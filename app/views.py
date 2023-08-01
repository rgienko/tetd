import os
from datetime import timedelta

import pandas
from django.contrib import auth, messages
from django.db.models import Sum, OuterRef, Subquery
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django_pandas.io import read_frame
from django.core.mail import EmailMessage
from django.db.models import F

from .filters import TimesheetFilter, ExpenseFilter, AdminTodoListFilter
from .models import *
from .forms import *


# Create your views here.
def login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = auth.authenticate(username=username, password=password)
        if user is not None:
            auth.login(request, user)
            if request.user.is_staff:
                return redirect('dashboard')
            else:
                return redirect('dashboard')
        else:
            messages.error(request, 'Error, wrong username or password.')
        return render(request, 'login.html')
    return render(request, 'login.html')


def register(request):
    if request.method == 'POST':
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')
        username = first_name + "." + last_name
        email = username + "@srgroupllc.com"
        if password1 == password2:
            new_user = User.objects.create_user(username, email, password1)
            new_user.first_name = first_name
            new_user.last_name = last_name
            new_user.save()

            return redirect('login')
        else:
            messages.error(request, 'Passwords do not match')
    else:
        pass

    return render(request, 'register.html')


def dashboard(request):
    user_info = get_object_or_404(User, pk=request.user.id)
    user_assignments = Assignments.objects.filter(employee_id=request.user.employee.employee_id).values('engagement_id')
    user_engagements = Engagement.objects.filter(engagement_id__in=user_assignments)

    today = date.today()
    week_beg = today - timedelta(days=today.weekday())
    week_end = week_beg + timedelta(days=5)

    timesheet_entries = Time.objects.all().filter(employee__user__username=request.user.username).filter(
        date__gte=week_beg).filter(date__lte=week_end).order_by('date')
    employee_td_entries = Todolist.objects.filter(employee__user__username=request.user.username).filter(
        todo_date__gte=week_beg).filter(todo_date__lte=week_end).order_by('todo_date')

    for engagement in user_engagements:
        engagement_ts_entries = Time.objects.filter(engagement=engagement.engagement_id)

        total_engagement_hours = engagement_ts_entries.aggregate(Sum('hours'))
        if total_engagement_hours['hours__sum'] is None:
            total_engagement_hours['hours__sum'] = 0

        engagement.total_engagement_bhours = engagement_ts_entries.filter(time_type_id='B').aggregate(Sum('hours'))

        engagement.total_engagement_nhours = engagement_ts_entries.filter(time_type_id='N').aggregate(Sum('hours'))

        engagement.total_engagement_hours = total_engagement_hours

        engagement.variance = engagement.budget_hours - total_engagement_hours['hours__sum']

        engagement.engagement_hours_by_employee = engagement_ts_entries.values(
            'employee__user__username',
            'employee__title__rate').annotate(
            engagement_employee_hours=Sum('hours'))

    context = {'user_engagements': user_engagements, 'today': today, 'week_beg': week_beg, 'week_end': week_end,
               'timesheet_entries': timesheet_entries, 'employee_td_entries': employee_td_entries,
               'user_info': user_info, 'user_assignments': user_assignments}
    return render(request, 'dashboard.html', context)


def adminDashboard(request):
    user_info = get_object_or_404(User, pk=request.user.id)
    parents = Parent.objects.all()

    # engagements = Engagement.objects.annotate(total_hours=Sum('time__hours'))

    engagements = Engagement.objects.values("engagement_id", "engagement_srg_id", "parent_id", "parent__parent_name",
                                            "provider_id", "provider__provider_name", "time_code",
                                            "time_code__time_code_desc",
                                            "is_complete", "fye", "budget_hours").annotate(
        engagement_hours_sum=Sum('time__hours')).order_by('engagement_hours_sum')

    engagement_billable = Time.objects.values("engagement_id").filter(time_type_id='B').annotate(
        bill_hours=Sum('hours'))
    engagement_non_billable = Time.objects.values("engagement_id").filter(time_type_id='N').annotate(
        non_bill_hours=Sum('hours'))

    # employee_ts_breakdown = Time.objects.values("engagement", "employee_id").annotate(total_ts_hours=Sum('hours'))
    # employee_td_breakdown = Todolist.objects.values("engagement", "employee_id").annotate(
    #    total_td_hours=Sum('anticipated_hours'))

    result = Time.objects.values('engagement_id', 'employee_id', 'employee__user__username',
                                 'employee__title__rate').annotate(
        TS_Hours=Sum('hours'),
        TD_Hours=Sum('engagement__todolist__anticipated_hours')
    ).filter(engagement_id=F('engagement'), employee_id=F('employee')).values(
        'engagement_id',
        'employee_id',
        'employee__user__username',
        'TS_Hours',
        'TD_Hours',
        'employee__title__rate'
    )

    if request.method == 'POST':
        createEngagementForm = CreateEngagementForm(request.POST)

        who = request.POST.get('provider')
        what = request.POST.get('time_code')
        when = request.POST.get('fye')
        how = request.POST.get('type')

        if when == '':
            engagement_srg_id = who + "." + str(what) + "." + how
        else:
            when = when[:4]
            engagement_srg_id = who + "." + str(what) + "." + str(when) + "." + how

        if createEngagementForm.is_valid():
            new_engagement = createEngagementForm.save(commit=False)
            new_engagement.engagement_srg_id = engagement_srg_id
            new_engagement.save()

            return redirect('admin-dashboard')
    else:
        createEngagementForm = CreateEngagementForm()

    context = {'user_info': user_info, 'parents': parents, 'createEngagementForm': createEngagementForm,
               'engagements': engagements, 'engagement_billable': engagement_billable,
               'engagement_non_billable': engagement_non_billable, "result": result}

    return render(request, 'adminDashboard.html', context)


def AdminTimesheet(request):
    user_info = get_object_or_404(User, pk=request.user.id)
    today = date.today()
    week_beg = today - timedelta(days=today.weekday())
    week_end = week_beg + timedelta(days=5)

    queryset = Time.objects.values('date', 'employee__user__username', 'engagement__engagement_srg_id',
                                   'engagement__parent__parent_name', 'engagement__provider',
                                   'engagement__provider__provider_name', 'engagement__time_code',
                                   'engagement__time_code__time_code_desc', 'hours', 'note').order_by('date')

    expense_queryset = Expense.objects.values('date', 'employee__user__username', 'engagement__engagement_srg_id',
                                              'expense_category', 'expense_amount').order_by('date')

    f = TimesheetFilter(request.GET, queryset=queryset)
    expense_filter = ExpenseFilter(request.GET, queryset=expense_queryset)

    if request.method == 'GET' and 'extract_button' in request.GET:
        ts_data = read_frame(f.qs)

        ex_data = read_frame(expense_filter.qs)

        fname = 'EmployeeTimesheetCompilation'

        response = HttpResponse(content_type='application/vns.ms-excel')
        response['Content-Disposition'] = 'attachment; filename=' + fname + '.xlsx'
        with pandas.ExcelWriter(response, engine='xlsxwriter') as writer:
            ts_data.to_excel(writer, sheet_name=('SRG Timesheet Compilation'), index=False, header=True)
            ex_data.to_excel(writer, sheet_name=('SRG Expense Compilation'), index=False, header=True)
            # df_hfy.to_excel(writer, sheet_name=('PFY ' + fye), index=False, header=True)

            return response

    context = {'filter': f, 'expense_filter': expense_filter, 'today': today, 'week_beg': week_beg,
               'week_end': week_end, 'user_info': user_info}
    return render(request, 'adminTimesheet.html', context)


def AdminPlanning(request):
    user_info = get_object_or_404(User, pk=request.user.id)
    period_beg = date.today()
    today = date.today()
    week_beg = today - timedelta(days=today.weekday())
    week_end = week_beg + timedelta(days=5)
    period_days = []
    for i in range(180):
        period_days.append(period_beg + timedelta(days=i))
    employees = Employee.objects.all()
    todolists = Todolist.objects.values('employee__user__username', 'engagement__provider',
                                        'engagement__provider__provider_name', 'todo_date',
                                        'engagement__engagement_srg_id', 'anticipated_hours').order_by('todo_date',
                                                                                                       'employee__user__username')

    todo_filter = AdminTodoListFilter(request.GET, queryset=todolists)

    if request.method == 'GET' and 'extract_button' in request.GET:
        ts_data = read_frame(todo_filter.qs)

        file_name = 'SRGToDoListCompilation'

        response = HttpResponse(content_type='application/vns.ms-excel')
        response['Content-Disposition'] = 'attachment; filename=' + file_name + '.xlsx'
        with pandas.ExcelWriter(response, engine='xlsxwriter') as writer:
            ts_data.to_excel(writer, sheet_name='SRG To-Do List Compilation', index=False, header=True)
            # ex_data.to_excel(writer, sheet_name=('SRG Expense Compilation'), index=False, header=True)
            # df_hfy.to_excel(writer, sheet_name=('PFY ' + fye), index=False, header=True)

            return response

    context = {'todolists': todolists, 'employees': employees, 'period_days': period_days,
               'todo_filter': todo_filter, 'week_beg': week_beg, 'week_end': week_end,
               'today': today, 'user_info': user_info}
    return render(request, 'adminPlanning.html', context)


def EmployeeTimesheet(request):
    user_info = get_object_or_404(User, pk=request.user.id)
    today = date.today()
    week_beg = today - timedelta(days=today.weekday())
    week_end = week_beg + timedelta(days=5)
    user_assignments = Assignments.objects.filter(employee_id=request.user.employee.employee_id).values('engagement_id')
    user_engagements = Engagement.objects.filter(engagement_id__in=user_assignments)

    current_employee = get_object_or_404(Employee, user_id=request.user.id)
    print(current_employee.employee_id)
    employee_ts_entries = Time.objects.filter(employee__user__username=request.user.username).filter(
        date__gte=week_beg).filter(date__lte=week_end).order_by('date')

    total_weekly_hours = employee_ts_entries.aggregate(Sum('hours'))

    current_week = []
    current_week_ts = {}

    for i in range(5):
        current_week.append(week_beg + timedelta(days=i))
        # current_week_ts['dow0'] = employee_ts_entries.filter(date=week_beg + timedelta(days=0))
        # current_week_ts['dow1'] = employee_ts_entries.filter(date=week_beg + timedelta(days=1))
        # current_week_ts['dow2'] = employee_ts_entries.filter(date=week_beg + timedelta(days=2))
        # current_week_ts['dow3'] = employee_ts_entries.filter(date=week_beg + timedelta(days=3))
        # current_week_ts['dow4'] = employee_ts_entries.filter(date=week_beg + timedelta(days=4))

    if request.method == 'POST':
        time_form = TimeForm(request.POST)
        expense_form = ExpenseForm(request.POST)
        todo_form = TodoForm(request.POST)
        if time_form.is_valid():
            engagement_id = request.POST.get('engagement-input')
            engagement_instance = get_object_or_404(Engagement, engagement_srg_id=engagement_id)

            employee_instance = get_object_or_404(Employee, user=request.user.id)

            new_entry = time_form.save(commit=False)
            new_entry.employee_id = employee_instance.employee_id
            new_entry.engagement = engagement_instance
            new_entry.save()

            engagement_hours = Time.objects.filter(engagement=engagement_instance.engagement_id).aggregate(
                ehours=Sum('hours')
            )

            if engagement_instance.budget_hours - engagement_hours['ehours'] <= 0:
                overBudgetAlert(engagement_instance.engagement_id)

            return redirect('employee-timesheet')

        elif expense_form.is_valid():
            employee_instance = get_object_or_404(Employee, user=request.user.id)
            engagement_id = request.POST.get('expense-input')
            engagement_instance = get_object_or_404(Engagement, engagement_srg_id=engagement_id)

            new_expense = expense_form.save(commit=False)
            new_expense.employee = employee_instance
            new_expense.engagement = engagement_instance

            new_expense.save()

            return redirect('employee-timesheet')

        elif todo_form.is_valid():
            employee_instance = get_object_or_404(Employee, user=request.user.id)
            engagement_id = request.POST.get('todo-input')
            engagement_instance = get_object_or_404(Engagement, engagement_srg_id=engagement_id)

            new_todo_item = todo_form.save(commit=False)
            new_todo_item.employee = employee_instance
            new_todo_item.engagement = engagement_instance

            new_todo_item.save()

            return redirect('employee-timesheet')
    else:
        time_form = TimeForm()
        expense_form = ExpenseForm()
        todo_form = TodoForm()

    context = {'employee_ts_entries': employee_ts_entries, 'week_beg': week_beg, 'week_end': week_end,
               'current_week': current_week, 'current_week_ts': current_week_ts, 'user_engagements': user_engagements,
               'time_form': time_form, 'expense_form': expense_form, 'todo_form': todo_form,
               'total_weekly_hours': total_weekly_hours, 'user_info': user_info}

    return render(request, 'employeeTimesheet.html', context)


def EmployeeTodolist(request):
    user_info = get_object_or_404(User, pk=request.user.id)
    today = date.today()
    week_beg = today - timedelta(days=today.weekday())
    week_end = week_beg + timedelta(days=5)
    user_assignments = Assignments.objects.filter(employee_id=request.user.employee.employee_id).values('engagement_id')
    user_engagements = Engagement.objects.filter(engagement_id__in=user_assignments)

    current_employee = get_object_or_404(Employee, user_id=request.user.id)
    employee_td_entries = Todolist.objects.filter(employee__user__username=request.user.username).filter(
        todo_date__gte=week_beg).filter(todo_date__lte=week_end).order_by('todo_date')

    current_week = []
    current_week_ts = {}

    for i in range(5):
        current_week.append(week_beg + timedelta(days=i))
        # current_week_ts['dow0'] = employee_ts_entries.filter(date=week_beg + timedelta(days=0))
        # current_week_ts['dow1'] = employee_ts_entries.filter(date=week_beg + timedelta(days=1))
        # current_week_ts['dow2'] = employee_ts_entries.filter(date=week_beg + timedelta(days=2))
        # current_week_ts['dow3'] = employee_ts_entries.filter(date=week_beg + timedelta(days=3))
        # current_week_ts['dow4'] = employee_ts_entries.filter(date=week_beg + timedelta(days=4))

    if request.method == 'POST':
        todo_form = TodoForm(request.POST)
        if todo_form.is_valid():
            engagement_id = request.POST.get('todo-input')
            engagement_instance = get_object_or_404(Engagement, engagement_srg_id=engagement_id)

            employee_instance = get_object_or_404(Employee, user=request.user.id)

            new_entry = todo_form.save(commit=False)
            new_entry.employee_id = employee_instance.employee_id
            new_entry.engagement = engagement_instance
            new_entry.save()

            return redirect('employee-todolist')
    else:
        todo_form = TodoForm()

    context = {'employee_td_entries': employee_td_entries, 'week_beg': week_beg, 'week_end': week_end,
               'todo_form': todo_form, 'user_info': user_info,
               'current_week': current_week, 'current_week_ts': current_week_ts, 'user_engagements': user_engagements}

    return render(request, 'employeeTodolist.html', context)


def EmployeeExpense(request):
    user_info = get_object_or_404(User, pk=request.user.id)
    today = date.today()
    week_beg = today - timedelta(days=today.weekday())
    week_end = week_beg + timedelta(days=5)

    current_employee = get_object_or_404(Employee, user_id=request.user.id)
    employee_expenses = Expense.objects.filter(employee__user__username=request.user.username).filter(
        date__gte=week_beg).filter(date__lte=week_end).order_by('date')

    total_expense = employee_expenses.aggregate(Sum('expense_amount'))

    context = {'employee_expenses': employee_expenses, 'week_beg': week_beg, 'week_end': week_end,
               'total_expense': total_expense, 'user_info': user_info}

    return render(request, 'employeeExpense.html', context)


def ExtractEngagementTimesheet(request, pk):
    engagement_instance = get_object_or_404(Engagement, pk=pk)

    queryset = Time.objects.filter(engagement=engagement_instance.engagement_id).values('date',
                                                                                        'employee__user__username',
                                                                                        'engagement__engagement_srg_id',
                                                                                        'engagement__parent__parent_name',
                                                                                        'engagement__provider',
                                                                                        'engagement__provider__provider_name',
                                                                                        'engagement__time_code',
                                                                                        'engagement__time_code__time_code_desc',
                                                                                        'hours', 'note')

    ts_data = read_frame(queryset)

    fname = 'EmployeeTimesheetCompilation'

    response = HttpResponse(content_type='application/vns.ms-excel')
    response['Content-Disposition'] = 'attachment; filename=' + fname + '.xlsx'
    with pandas.ExcelWriter(response, engine='xlsxwriter') as writer:
        ts_data.to_excel(writer, sheet_name=('SRG Timesheet Compilation'), index=False, header=True)
        # df_hfy.to_excel(writer, sheet_name=('PFY ' + fye), index=False, header=True)

        return response


def UpdateEngagementStatus(request, pk):
    engagement_instance = get_object_or_404(Engagement, pk=pk)
    if engagement_instance.is_complete is False:
        engagement_instance.is_complete = True
        engagement_instance.save()
    else:
        engagement_instance.is_complete = False
        engagement_instance.save()

    return redirect('admin-dashboard')


def AssignmentProjects(request, pk):
    engagement_instance = get_object_or_404(Engagement, pk=pk)
    eid = engagement_instance.engagement_id
    engagement_assignments = Assignments.objects.filter(engagement=engagement_instance)
    available_staff = Employee.objects.raw(
        """
            SELECT *
            FROM app_employee
            WHERE employee_id NOT IN (SELECT employee_id FROM app_assignments WHERE engagement_id = %s);
        """, [eid]
    )

    context = {'engagement_assignments': engagement_assignments, 'engagement_instance': engagement_instance,
               'available_staff': available_staff}

    return render(request, 'assign.html', context)


def AddAssignment(request, eng, emp):
    engagement_instance = get_object_or_404(Engagement, pk=eng)
    employee_instance = get_object_or_404(Employee, pk=emp)

    new_assignment = Assignments(engagement=engagement_instance, employee=employee_instance)
    new_assignment.save()

    return redirect('admin-assign', eng)


def RemoveAssignment(request, eng, emp):
    engagement_instance = get_object_or_404(Engagement, pk=eng)
    employee_instance = get_object_or_404(Employee, pk=emp)
    assignment_instance = get_object_or_404(Assignments, employee=emp, engagement=engagement_instance)

    assignment_instance.delete()

    return redirect('admin-assign', eng)


def overBudgetAlert(pk):
    SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY')
    engagement_instance = get_object_or_404(Engagement, pk=pk)

    engagement_id = engagement_instance.engagement_srg_id
    engagement_provider = str(engagement_instance.provider_id) + "-" + engagement_instance.getProviderName()
    engagement_scope = str(engagement_instance.time_code) + "-" + engagement_instance.getTCDesc()
    engagement_fye = str(engagement_instance.fye)

    msg = EmailMessage(
        from_email='Randall.Gienko@srgroupllc.com',
        to=['Randall.Gienko@srgroupllc.com', 'Trahan.Whitten@srgroupllc.com']
    )

    protocol = 'http://'
    engagement_url = 'localhost:8000/admin_engagement_detail/' + str(engagement_instance.engagement_id) + '/'

    msg.template_id = "d-72ebc0569ab6402fa236d9cdc75a860b"
    msg.dynamic_template_data = {
        "title": 'Engagement Over Budget',
        "protocol": protocol,
        "engagement_url": engagement_url,
        "engagement_id": engagement_id,
        "engagement_provider": engagement_provider,
        "engagement_scope": engagement_scope,
        # "engagement_budget": engagement_budget,
        "engagement_fye": engagement_fye
    }

    # msg.SendGridAPIClient(SENDGRID_API_KEY)
    msg.send(fail_silently=False)
    # sg = SendGridAPIClient(SENDGRID_API_KEY)
    # response = sg.send(msg)
