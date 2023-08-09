import os
from datetime import timedelta
from itertools import chain

import pandas
from django.contrib import auth, messages
from django.db.models import Sum, OuterRef, Subquery, Max, Count, ExpressionWrapper, CharField, FloatField, \
    IntegerField, Case, Value, When, Q
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django_pandas.io import read_frame
from django.core.mail import EmailMessage
from django.db.models import F
from dateutil.relativedelta import relativedelta

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


def getCompilationData(mnth):
    fixed_hours_by_employee = Time.objects.filter(engagement__type_id='F', date__month=mnth).values(
        'employee_id', 'employee__title').annotate(
        fixed_hours_by_employee_sum=Sum('hours')
    )

    hourly_hours_by_employee = Time.objects.filter(engagement__type_id='H', date__month=mnth).values(
        'employee_id', 'employee__title').annotate(
        hourly_hours_by_employee_sum=Sum('hours')
    )

    cgy_hours_by_employee = Time.objects.filter(engagement__type_id='C', date__month=mnth).values(
        'employee_id').annotate(
        cgy_hours_by_employee_sum=Sum('hours')
    )

    non_billable_hours_by_employee = Time.objects.filter(time_type_id='N', date__month=mnth).values(
        'employee_id').annotate(non_billable_hours_sum=Sum('hours'))

    pto_hours_by_employee = Time.objects.filter(engagement__time_code=945, date__month=mnth).values(
        'employee_id').annotate(
        pto_hours_by_employee_sum=Sum('hours')
    )

    billable_hours_by_employee = Time.objects.filter(time_type_id='B', date__month=mnth).values(
        'employee_id').annotate(
        billable_hours_sum=Sum('hours'))

    total_hours_by_employee = Time.objects.filter(date__month=mnth).values('employee_id').annotate(
        total_hours_sum=Sum('hours'))

    # VP HOURS ##########
    vp_fixed_hours_by_employee = fixed_hours_by_employee.filter(employee__title='VP')
    vp_hourly_hours_by_employee = hourly_hours_by_employee.filter(Q(employee__title='EVP') | Q(employee__title='VP'))
    vp_cgy_hours_by_employee = cgy_hours_by_employee.filter(Q(employee__title='EVP') | Q(employee__title='VP'))
    vp_non_billable_hours_by_employee = non_billable_hours_by_employee.filter(Q(employee__title='EVP') | Q(employee__title='VP'))
    vp_pto_hours_by_employee = pto_hours_by_employee.filter(Q(employee__title='EVP') | Q(employee__title='VP'))
    vp_billable_hours_by_employee = billable_hours_by_employee.filter(Q(employee__title='EVP') | Q(employee__title='VP'))
    vp_total_hours_by_employee = total_hours_by_employee.filter(Q(employee__title='EVP') | Q(employee__title='VP'))

    vp_total_fixed_hours = vp_fixed_hours_by_employee.aggregate(Sum('fixed_hours_by_employee_sum'))
    vp_total_hourly_hours = vp_hourly_hours_by_employee.aggregate(Sum('hourly_hours_by_employee_sum'))
    vp_total_cgy_hours = vp_cgy_hours_by_employee.aggregate(Sum('cgy_hours_by_employee_sum'))
    vp_total_non_billable_hours = vp_non_billable_hours_by_employee.aggregate(Sum('non_billable_hours_sum'))
    vp_total_pto_hours = vp_pto_hours_by_employee.aggregate(Sum('pto_hours_by_employee_sum'))
    vp_total_billable_hours = vp_billable_hours_by_employee.aggregate(Sum('billable_hours_sum'))
    vp_total_hours = vp_total_hours_by_employee.aggregate(Sum('total_hours_sum'))

    # TOTAL HOURS ###
    srg_total_fixed_hours = vp_total_fixed_hours
    srg_total_hourly_hours = vp_total_hourly_hours
    srg_total_cgy_hours = vp_total_cgy_hours
    srg_total_non_billable_hours = vp_total_non_billable_hours
    srg_total_pto_hours = vp_total_pto_hours
    srg_total_billable_hours = vp_total_billable_hours
    srg_total_hours = vp_total_hours

    return vp_fixed_hours_by_employee, vp_hourly_hours_by_employee, vp_cgy_hours_by_employee,\
        vp_non_billable_hours_by_employee, vp_pto_hours_by_employee, vp_billable_hours_by_employee, \
        vp_total_hours_by_employee, vp_total_fixed_hours, vp_total_hourly_hours, vp_total_cgy_hours, \
        vp_total_non_billable_hours, vp_total_pto_hours, vp_total_billable_hours, vp_total_hours


def AdminDashboard(request):
    user_info = get_object_or_404(User, pk=request.user.id)
    today = date.today()
    week_beg = today - timedelta(days=today.weekday())
    week_end = week_beg + timedelta(days=5)
    employees = Employee.objects.all().order_by('title', 'user__last_name')
    vps = employees.filter(title='VP')
    mgrs = employees.filter(Q(title='M') | Q(title='SM'))
    consultants = employees.filter(Q(title='C') | Q(title='SC'))
    current_month = today.month
    print(current_month)

    if request.method == 'POST':
        month_form = MonthSelectForm(request.POST)
        if month_form.is_valid():
            selected_month = month_form.cleaned_data['month']
            new_data = getCompilationData(selected_month)

            context = {'user_info': user_info, 'today': today, 'week_beg': week_beg,
                       'week_end': week_end, 'employees': employees, 'vps': vps,
                       'mgrs': mgrs, 'consultants': consultants,
                       'vp_fixed_hours_by_employee': new_data[0],
                       'vp_hourly_hours_by_employee': new_data[1],
                       'vp_cgy_hours_by_employee': new_data[2],
                       'selected_month': selected_month,
                       'month_form': month_form}

            return render(request, 'adminDashboard.html', context)

    else:
        month_form = MonthSelectForm(initial={'month': current_month})
        current_month_data = getCompilationData(current_month)

        context = {'user_info': user_info, 'today': today, 'week_beg': week_beg,
                   'week_end': week_end, 'employees': employees, 'vps': vps,
                   'mgrs': mgrs, 'consultants': consultants,
                   'vp_fixed_hours_by_employee': current_month_data[0],
                   'vp_hourly_hours_by_employee': current_month_data[1],
                   'vp_cgy_hours_by_employee': current_month_data[2],
                   'vp_non_billable_hours_by_employee': current_month_data[3],
                   'vp_pto_hours_by_employee': current_month_data[4],
                   'vp_billable_hours_by_employee': current_month_data[5],
                   'vp_total_hours_by_employee': current_month_data[6],
                   'vp_total_fixed_hours': current_month_data[7],
                   'vp_total_hourly_hours': current_month_data[8],
                   'vp_total_cgy_hours': current_month_data[9],
                   'vp_total_non_billable_hours': current_month_data[10],
                   'vp_total_pto_hours': current_month_data[11],
                   'vp_total_billable_hours': current_month_data[12],
                   'vp_total_hours': current_month_data[13],
                   'selected_month': today,
                   'month_form': month_form}

        return render(request, 'adminDashboard.html', context)


def EngagementDashboard(request):
    user_info = get_object_or_404(User, pk=request.user.id)
    parents = list(Parent.objects.all())
    parents = sorted(parents, key=lambda x: (x.parent_id.isdigit(), x.parent_id))

    # engagements = Engagement.objects.annotate(total_hours=Sum('time__hours'))

    engagements = Engagement.objects.values("engagement_id", "engagement_srg_id", "parent_id", "parent__parent_name",
                                            "provider_id", "provider__provider_name", "time_code",
                                            "time_code__time_code_desc",
                                            "is_complete", "fye", "budget_hours", "budget_amount").annotate(
        engagement_hours_sum=Sum('time__hours'), budget_calc=Max('budget_amount') / 250).order_by('-fye', 'time_code',
                                                                                                  'provider_id',
                                                                                                  'engagement_hours_sum')

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
               'engagements': engagements}

    return render(request, 'engagementDashboard.html', context)


def AdminEngagementDetail(request, pk):
    user_info = get_object_or_404(User, pk=request.user.id)
    engagement_instance = get_object_or_404(Engagement, pk=pk)

    budget_calc = engagement_instance.budget_amount // 250

    billable_hours_employee = Time.objects.filter(engagement=engagement_instance.engagement_id,
                                                  time_type_id='B').values('engagement',
                                                                           'employee__user__username').annotate(
        billable_hours_sum=Sum('hours'))
    non_billable_hours_employee = Time.objects.filter(engagement=engagement_instance.engagement_id,
                                                      time_type_id='N').values('engagement',
                                                                               'employee__user__username').annotate(
        non_billable_hours_sum=Sum('hours'))

    total_billable_hours = billable_hours_employee.aggregate(Sum('billable_hours_sum'))
    total_non_billable_hours = non_billable_hours_employee.aggregate(Sum('non_billable_hours_sum'))

    engagement_td_hours_by_employee = Todolist.objects.filter(engagement=engagement_instance.engagement_id).values(
        'engagement', 'employee__user__username').annotate(td_hours=Sum('anticipated_hours')).values('td_hours')

    engagement_ts_hours_by_employee = Time.objects.filter(engagement=engagement_instance.engagement_id).values(
        'engagement', 'employee__user__username').annotate(ts_hours=Sum('hours')).values('ts_hours')

    ts_vs_todo = Engagement.objects.raw('''
                                        SELECT 
                                            ae.engagement_id,
                                            ae.engagement_srg_id,
                                               ae.parent_id,
                                               ae.provider_id,
                                               at.username AS TS_EMP,
                                               SUM(at.sum_hours) AS TS_HOURS,
                                               tl.username AS TD_EMP,
                                               SUM(tl.td_sum_hours) AS TD_HOURS
                                        FROM app_engagement ae
                                        FULL JOIN (
                                            SELECT srg_id,
                                                   au.username,
                                                   SUM(hours) AS sum_hours
                                            FROM app_time
                                            JOIN app_employee on app_time.employee_id = app_employee.employee_id
                                            JOIN auth_user au on app_employee.user_id = au.id
                                            GROUP BY srg_id, au.username
                                        ) at on ae.engagement_id = at.srg_id
                                        FULL JOIN (
                                            SELECT srg_id,
                                                   au.username,
                                                   SUM(anticipated_hours) AS td_sum_hours
                                            FROM app_todolist
                                            JOIN app_employee on app_todolist.employee_id = app_employee.employee_id
                                            JOIN auth_user au on app_employee.user_id = au.id
                                            GROUP BY srg_id, au.username
                                        ) tl on ae.engagement_id = tl.srg_id
                                        WHERE ae.engagement_srg_id = %s
                                        GROUP BY ae.engagement_id, ae.engagement_srg_id, ae.parent_id, ae.provider_id, at.username, tl.username
                                        ORDER BY ae.parent_id, ae.provider_id
                                        ''', [engagement_instance.engagement_srg_id])

    context = {'user_info': user_info, 'engagement_instance': engagement_instance,
               'billable_hours_employee': billable_hours_employee, 'total_billable_hours': total_billable_hours,
               'non_billable_hours_employee': non_billable_hours_employee, 'budget_calc': budget_calc,
               'total_non_billable_hours': total_non_billable_hours, 'ts_vs_todo': ts_vs_todo}

    return render(request, 'adminEngagementDetail.html', context)


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
    user_info = get_object_or_404(User, pk=request.user.id)
    engagement_instance = get_object_or_404(Engagement, pk=pk)
    eid = engagement_instance.engagement_id
    engagement_assignments = Assignments.objects.filter(engagement=engagement_instance).order_by('employee__user')

    available_staff = Employee.objects.exclude(
        employee_id__in=engagement_assignments.values('employee_id').filter(engagement=eid)
    ).order_by('user__first_name')

    # available_staff = available_staff

    context = {'engagement_assignments': engagement_assignments, 'engagement_instance': engagement_instance,
               'available_staff': available_staff, 'user_info': user_info}

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


def RenewEngagement(request, pk):
    engagement_instance = get_object_or_404(Engagement, pk=pk)
    parent_instance = get_object_or_404(Parent, pk=engagement_instance.parent_id)
    provider_instance = get_object_or_404(Provider, pk=engagement_instance.provider_id)
    time_code_instance = get_object_or_404(Timecode, pk=engagement_instance.time_code_id)
    bill_type_instance = get_object_or_404(BillingTypes, pk=engagement_instance.type_id)
    new_start_date = engagement_instance.start_date + relativedelta(years=1)
    new_fye = engagement_instance.fye + relativedelta(years=1)
    new_budget_amount = engagement_instance.budget_amount
    new_budget_hours = engagement_instance.budget_hours
    is_complete = False
    new_parent = parent_instance
    new_provider = provider_instance
    new_time_code = time_code_instance
    new_bill_type = bill_type_instance

    who = new_provider.provider_id
    what = new_time_code.time_code
    when = new_fye
    how = new_bill_type.type_id

    if when == '':
        new_engagement_srg_id = str(who) + "." + str(what) + "." + str(how)
    else:
        when = when.year
        new_engagement_srg_id = str(who) + "." + str(what) + "." + str(when) + "." + str(how)

    new_engagement = Engagement(engagement_srg_id=new_engagement_srg_id, start_date=new_start_date, fye=new_fye,
                                budget_amount=new_budget_amount, budget_hours=new_budget_hours, is_complete=is_complete,
                                parent=new_parent, provider=new_provider, time_code=new_time_code, type=new_bill_type)

    new_engagement.save()

    return redirect('admin-dashboard')
    # new_engagement = Engagement()


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


# Archived Functions #
'''
def adminDashboardArchive(request):
    user_info = get_object_or_404(User, pk=request.user.id)
    parents = list(Parent.objects.all())
    parents = sorted(parents, key=lambda x: (x.parent_id.isdigit(), x.parent_id))

    # engagements = Engagement.objects.annotate(total_hours=Sum('time__hours'))

    engagements = Engagement.objects.values("engagement_id", "engagement_srg_id", "parent_id", "parent__parent_name",
                                            "provider_id", "provider__provider_name", "time_code",
                                            "time_code__time_code_desc",
                                            "is_complete", "fye", "budget_hours", "budget_amount").annotate(
        engagement_hours_sum=Sum('time__hours'), budget_calc=Max('budget_amount') / 250).order_by('-fye', 'time_code',
                                                                                                  'provider_id',
                                                                                                  'engagement_hours_sum')

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
    ).distinct().order_by('engagement', 'employee_id')

    # result = Time.objects.values('engagement_id', 'employee_id', 'employee__user__username',
    #                            'employee__title__rate').annotate(TS_Hours=Sum('hours'))

    ts_hours_qs = Time.objects.filter(engagement_id=OuterRef('engagement_id'),
                                      employee_id=OuterRef('employee_id')).values(
        'engagement_id', 'employee_id').annotate(TS_Hours=Sum('hours')).values('TS_Hours')

    td_hours_qs = Todolist.objects.filter(engagement_id=OuterRef('engagement_id'),
                                          employee_id=OuterRef('employee_id')).values(
        'engagement_id', 'employee_id').annotate(TD_Hours=Sum('anticipated_hours')).values('TD_Hours')

    result = Todolist.objects.values('engagement_id', 'employee_id', 'employee__user__username',
                                     'employee__title__rate').annotate(
        TS_Hours=Subquery(ts_hours_qs, output_field=IntegerField()),
        TD_Hours=Sum('anticipated_hours')
    ).annotate(
        Rate=Case(
            When(TS_Hours=0, then=Value(0)),
            default=F('TS_Hours') / F('TD_Hours'),
            output_field=FloatField()
        )
    )

    result_qs = Engagement.objects.annotate(
        engagement=F('engagement_id'),
        par=F('parent_id'),
        prov=F('provider_id'),
        # TS_EMP=F('engagement_id__time__employee_id'),
        TS_HOURS=Subquery(ts_hours_qs, output_field=IntegerField()),
        # TD_EMP=F('engagement_id__todolist__employee_id'),
        TD_HOURS=Subquery(td_hours_qs, output_field=IntegerField())
    ).filter(
        Q(time__srg_id__in=Subquery(ts_hours_qs.values('engagement_id'))) |
        Q(todolist__srg_id__in=Subquery(td_hours_qs.values('engagement_id')))
    ).distinct().order_by('parent_id', 'provider_id')

    # Access the results from the queryset
    for item in result_qs:
        engagement_srg_id = item.engagement_srg_id
        parent_id = item.parent_id
        provider_id = item.provider_id
        ts_emp = item.TS_EMP
        ts_hours = item.TS_HOURS
        td_emp = item.TD_EMP
        td_hours = item.TD_HOURS

        print(f"Engagement SRG ID: {engagement_srg_id}, Parent ID: {parent_id}, Provider ID: {provider_id}")
        print(f"TS Employee ID: {ts_emp}, TS Hours: {ts_hours}")
        print(f"TD Employee ID: {td_emp}, TD Hours: {td_hours}")

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
               'engagement_non_billable': engagement_non_billable, "result": result, 'td_hours_qs': td_hours_qs}

    return render(request, 'adminDashboard.html', context)
'''
