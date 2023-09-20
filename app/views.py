import datetime
import os
from datetime import timedelta
from io import BytesIO

import pandas
from dateutil.relativedelta import relativedelta
from django.contrib import auth, messages
from django.core.mail import EmailMessage
from django.core.paginator import Paginator
from django.db.models import F
from django.db.models import Max, Case, When, Q, DecimalField
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django_pandas.io import read_frame
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from .filters import TimesheetFilter, ExpenseFilter, AdminTodoListFilter
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
                return redirect('admin-dashboard')
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
    ts_is_submitted = user_info.employee.ts_is_submitted
    user_assignments = Assignments.objects.filter(employee_id=user_info.employee.employee_id).values('engagement_id')
    # user_engagements = Engagement.objects.filter(engagement_id__in=user_assignments)

    user_engagements = Engagement.objects.values("engagement_id", "engagement_srg_id", "parent_id",
                                                 "parent__parent_name",
                                                 "provider_id", "provider__provider_name", "time_code",
                                                 "time_code__time_code_desc",
                                                 "is_complete", "fye", "budget_hours", "budget_amount").annotate(
        engagement_hours_sum=Coalesce(Sum('time__hours'), 0, output_field=DecimalField(0.00)),
        budget_calc=Max('budget_amount') / 250).filter(
        engagement_id__in=user_assignments).order_by('-fye', 'time_code',
                                                     'provider_id',
                                                     'engagement_hours_sum')

    today = date.today()
    week_beg = today - timedelta(days=today.weekday())
    week_end = week_beg + timedelta(days=5)

    timesheet_entries = Time.objects.all().filter(employee__user__username=request.user.username).filter(
        ts_date__gte=week_beg).filter(ts_date__lte=week_end)

    billable_hours_sum = timesheet_entries.exclude(Q(engagement__type_id='N') | Q(time_type_id_id='N')).aggregate(
        amount=Coalesce(Sum('hours'), 0, output_field=DecimalField(0.00)))

    non_billable_hours_sum = timesheet_entries.filter(Q(engagement__type_id='N') | Q(time_type_id_id='N')).aggregate(
        amount=Coalesce(Sum('hours'), 0, output_field=DecimalField(0.00)))

    employee_td_entries = Todolist.objects.values('todo_date',
                                                  'engagement__parent_id',
                                                  'engagement__parent_id__parent_name',
                                                  'engagement__provider_id',
                                                  'engagement__provider_id__provider_name',
                                                  'engagement__time_code',
                                                  'engagement__time_code__time_code_desc').filter(
        employee__user__username=request.user.username).filter(todo_date=today).order_by('todo_date').annotate(
        hsum=Sum('anticipated_hours'))

    context = {'user_engagements': user_engagements, 'today': today, 'week_beg': week_beg, 'week_end': week_end,
               'timesheet_entries': timesheet_entries, 'employee_td_entries': employee_td_entries,
               'user_info': user_info, 'user_assignments': user_assignments, 'billable_hours_sum': billable_hours_sum,
               'non_billable_hours_sum': non_billable_hours_sum, 'ts_is_submitted': ts_is_submitted}
    return render(request, 'dashboard.html', context)


def getCompilationData(mnth):
    if mnth == 'YTD':
        fixed_hours_by_employee = Time.objects.filter(engagement__type_id='F', ts_date__year=date.today().year).values(
            'employee_id', 'employee__title').annotate(
            fixed_hours_by_employee_sum=Sum('hours')
        )

        hourly_hours_by_employee = Time.objects.filter(engagement__type_id='H', ts_date__year=date.today().year).values(
            'employee_id', 'employee__title').annotate(
            hourly_hours_by_employee_sum=Sum('hours')
        )

        cgy_hours_by_employee = Time.objects.filter(engagement__type_id='C', ts_date__year=date.today().year).values(
            'employee_id').annotate(
            cgy_hours_by_employee_sum=Sum('hours')
        )

        non_billable_hours_by_employee = Time.objects.filter(time_type_id='N', ts_date__year=date.today().year).values(
            'employee_id').annotate(non_billable_hours_sum=Sum('hours'))

        pto_hours_by_employee = Time.objects.filter(engagement__time_code=945, ts_date__year=date.today().year).values(
            'employee_id').annotate(
            pto_hours_by_employee_sum=Sum('hours')
        )

        billable_hours_by_employee = Time.objects.filter(time_type_id='B', ts_date__year=date.today().year).values(
            'employee_id').annotate(
            billable_hours_sum=Sum('hours'))

        total_hours_by_employee = Time.objects.filter(ts_date__year=date.today().year).values('employee_id').annotate(
            total_hours_sum=Sum('hours'))
    else:
        fixed_hours_by_employee = Time.objects.filter(engagement__type_id='F', ts_date__month=mnth).values(
            'employee_id', 'employee__title').annotate(
            fixed_hours_by_employee_sum=Sum('hours')
        )

        hourly_hours_by_employee = Time.objects.filter(engagement__type_id='H', ts_date__month=mnth).values(
            'employee_id', 'employee__title').annotate(
            hourly_hours_by_employee_sum=Sum('hours')
        )

        cgy_hours_by_employee = Time.objects.filter(engagement__type_id='C', ts_date__month=mnth).values(
            'employee_id', 'employee__title').annotate(
            cgy_hours_by_employee_sum=Sum('hours')
        )

        non_billable_hours_by_employee = Time.objects.filter(Q(time_type_id='N') | Q(engagement__type_id='N'),
                                                             ts_date__month=mnth).values(
            'employee_id').annotate(non_billable_hours_sum=Sum('hours'))

        pto_hours_by_employee = Time.objects.filter(engagement__time_code=945, ts_date__month=mnth).values(
            'employee_id').annotate(
            pto_hours_by_employee_sum=Sum('hours')
        )

        billable_hours_by_employee = Time.objects.filter(time_type_id='B', ts_date__month=mnth).values(
            'employee_id').annotate(
            billable_hours_sum=Sum('hours'))

        total_hours_by_employee = Time.objects.filter(ts_date__month=mnth).values('employee_id').annotate(
            total_hours_sum=Sum('hours'))

    # VP HOURS ##########
    vp_fixed_hours_by_employee = fixed_hours_by_employee.filter(employee__title='VP')
    vp_hourly_hours_by_employee = hourly_hours_by_employee.filter(Q(employee__title='EVP') | Q(employee__title='VP'))
    vp_cgy_hours_by_employee = cgy_hours_by_employee.filter(Q(employee__title='EVP') | Q(employee__title='VP'))
    vp_non_billable_hours_by_employee = non_billable_hours_by_employee.filter(
        Q(employee__title='EVP') | Q(employee__title='VP'))
    vp_pto_hours_by_employee = pto_hours_by_employee.filter(Q(employee__title='EVP') | Q(employee__title='VP'))
    vp_billable_hours_by_employee = billable_hours_by_employee.filter(
        Q(employee__title='EVP') | Q(employee__title='VP'))
    vp_total_hours_by_employee = total_hours_by_employee.filter(Q(employee__title='EVP') | Q(employee__title='VP'))

    vp_total_fixed_hours = vp_fixed_hours_by_employee.aggregate(
        amount=Coalesce(Sum('fixed_hours_by_employee_sum'), 0, output_field=DecimalField(0.00)))
    vp_total_hourly_hours = vp_hourly_hours_by_employee.aggregate(
        amount=Coalesce(Sum('hourly_hours_by_employee_sum'), 0, output_field=DecimalField(0.00)))
    vp_total_cgy_hours = vp_cgy_hours_by_employee.aggregate(
        amount=Coalesce(Sum('cgy_hours_by_employee_sum'), 0, output_field=DecimalField(0.00)))
    vp_total_non_billable_hours = vp_non_billable_hours_by_employee.aggregate(
        amount=Coalesce(Sum('non_billable_hours_sum'), 0, output_field=DecimalField(0.00)))
    vp_total_pto_hours = vp_pto_hours_by_employee.aggregate(
        amount=Coalesce(Sum('pto_hours_by_employee_sum'), 0, output_field=DecimalField(0.00)))
    vp_total_billable_hours = vp_billable_hours_by_employee.aggregate(
        amount=Coalesce(Sum('billable_hours_sum'), 0, output_field=DecimalField(0.00)))
    vp_total_hours = vp_total_hours_by_employee.aggregate(
        amount=Coalesce(Sum('total_hours_sum'), 0, output_field=DecimalField(0.00)))

    # ####################################### SENIOR MANAGERS HOURS ###################################################
    smgr_fixed_hours_by_employee = fixed_hours_by_employee.filter(employee__title='SM')
    smgr_hourly_hours_by_employee = hourly_hours_by_employee.filter(employee__title='SM')
    smgr_cgy_hours_by_employee = cgy_hours_by_employee.filter(employee__title='SM')
    smgr_non_billable_hours_by_employee = non_billable_hours_by_employee.filter(employee__title='SM')
    smgr_pto_hours_by_employee = pto_hours_by_employee.filter(employee__title='SM')
    smgr_billable_hours_by_employee = billable_hours_by_employee.filter(employee__title='SM')
    smgr_total_hours_by_employee = total_hours_by_employee.filter(employee__title='SM')

    smgr_total_fixed_hours = smgr_fixed_hours_by_employee.aggregate(
        amount=Coalesce(Sum('fixed_hours_by_employee_sum'), 0, output_field=DecimalField(0.00)))
    smgr_total_hourly_hours = smgr_hourly_hours_by_employee.aggregate(
        amount=Coalesce(Sum('hourly_hours_by_employee_sum'), 0, output_field=DecimalField(0.00)))
    smgr_total_cgy_hours = smgr_cgy_hours_by_employee.aggregate(
        amount=Coalesce(Sum('cgy_hours_by_employee_sum'), 0, output_field=DecimalField(0.00)))
    smgr_total_non_billable_hours = smgr_non_billable_hours_by_employee.aggregate(
        amount=Coalesce(Sum('non_billable_hours_sum'), 0, output_field=DecimalField(0.00)))
    smgr_total_pto_hours = smgr_pto_hours_by_employee.aggregate(
        amount=Coalesce(Sum('pto_hours_by_employee_sum'), 0, output_field=DecimalField(0.00)))
    smgr_total_billable_hours = smgr_billable_hours_by_employee.aggregate(
        amount=Coalesce(Sum('billable_hours_sum'), 0, output_field=DecimalField(0.00)))
    smgr_total_hours = smgr_total_hours_by_employee.aggregate(
        amount=Coalesce(Sum('total_hours_sum'), 0, output_field=DecimalField(0.00)))

    # ####################################### MGRS HOURS ##############################################################
    mgr_fixed_hours_by_employee = fixed_hours_by_employee.filter(employee__title='M')
    mgr_hourly_hours_by_employee = hourly_hours_by_employee.filter(employee__title='M')
    mgr_cgy_hours_by_employee = cgy_hours_by_employee.filter(employee__title='M')
    mgr_non_billable_hours_by_employee = non_billable_hours_by_employee.filter(employee__title='M')
    mgr_pto_hours_by_employee = pto_hours_by_employee.filter(employee__title='M')
    mgr_billable_hours_by_employee = billable_hours_by_employee.filter(employee__title='M')
    mgr_total_hours_by_employee = total_hours_by_employee.filter(employee__title='M')

    mgr_total_fixed_hours = mgr_fixed_hours_by_employee.aggregate(
        amount=Coalesce(Sum('fixed_hours_by_employee_sum'), 0, output_field=DecimalField(0.00)))
    mgr_total_hourly_hours = mgr_hourly_hours_by_employee.aggregate(
        amount=Coalesce(Sum('hourly_hours_by_employee_sum'), 0, output_field=DecimalField(0.00)))
    mgr_total_cgy_hours = mgr_cgy_hours_by_employee.aggregate(
        amount=Coalesce(Sum('cgy_hours_by_employee_sum'), 0, output_field=DecimalField(0.00)))
    mgr_total_non_billable_hours = mgr_non_billable_hours_by_employee.aggregate(
        amount=Coalesce(Sum('non_billable_hours_sum'), 0, output_field=DecimalField(0.00)))
    mgr_total_pto_hours = mgr_pto_hours_by_employee.aggregate(
        amount=Coalesce(Sum('pto_hours_by_employee_sum'), 0, output_field=DecimalField(0.00)))
    mgr_total_billable_hours = mgr_billable_hours_by_employee.aggregate(
        amount=Coalesce(Sum('billable_hours_sum'), 0, output_field=DecimalField(0.00)))
    mgr_total_hours = mgr_total_hours_by_employee.aggregate(
        amount=Coalesce(Sum('total_hours_sum'), 0, output_field=DecimalField(0.00)))

    # ####################################### CONSULTANT HOURS ########################################################
    c_fixed_hours_by_employee = fixed_hours_by_employee.filter(Q(employee__title_id='C') | Q(employee__title='SC'))
    c_hourly_hours_by_employee = hourly_hours_by_employee.filter(Q(employee__title='C') | Q(employee__title='SC'))
    c_cgy_hours_by_employee = cgy_hours_by_employee.filter(Q(employee__title='C') | Q(employee__title='SC'))
    c_non_billable_hours_by_employee = non_billable_hours_by_employee.filter(
        Q(employee__title='C') | Q(employee__title='SC'))
    c_pto_hours_by_employee = pto_hours_by_employee.filter(Q(employee__title='C') | Q(employee__title='SC'))
    c_billable_hours_by_employee = billable_hours_by_employee.filter(
        Q(employee__title='C') | Q(employee__title='SC'))
    c_total_hours_by_employee = total_hours_by_employee.filter(Q(employee__title='C') | Q(employee__title='SC'))

    c_total_fixed_hours = c_fixed_hours_by_employee.aggregate(
        amount=Coalesce(Sum('fixed_hours_by_employee_sum'), 0, output_field=DecimalField(0.00)))
    c_total_hourly_hours = c_hourly_hours_by_employee.aggregate(
        amount=Coalesce(Sum('hourly_hours_by_employee_sum'), 0, output_field=DecimalField(0.00)))
    c_total_cgy_hours = c_cgy_hours_by_employee.aggregate(
        amount=Coalesce(Sum('cgy_hours_by_employee_sum'), 0, output_field=DecimalField(0.00)))
    c_total_non_billable_hours = c_non_billable_hours_by_employee.aggregate(
        amount=Coalesce(Sum('non_billable_hours_sum'), 0, output_field=DecimalField(0.00)))
    c_total_pto_hours = c_pto_hours_by_employee.aggregate(
        amount=Coalesce(Sum('pto_hours_by_employee_sum'), 0, output_field=DecimalField(0.00)))
    c_total_billable_hours = c_billable_hours_by_employee.aggregate(
        amount=Coalesce(Sum('billable_hours_sum'), 0, output_field=DecimalField(0.00)))
    c_total_hours = c_total_hours_by_employee.aggregate(
        amount=Coalesce(Sum('total_hours_sum'), 0, output_field=DecimalField(0.00)))

    # TOTAL HOURS ###
    srg_total_fixed_hours = vp_total_fixed_hours['amount'] + mgr_total_fixed_hours['amount'] + c_total_fixed_hours[
        'amount']
    srg_total_hourly_hours = vp_total_hourly_hours['amount'] + mgr_total_hourly_hours['amount'] + c_total_hourly_hours[
        'amount']
    srg_total_cgy_hours = vp_total_cgy_hours['amount'] + mgr_total_cgy_hours['amount'] + c_total_cgy_hours['amount']
    srg_total_non_billable_hours = vp_total_non_billable_hours['amount'] + mgr_total_non_billable_hours['amount'] + \
                                   c_total_non_billable_hours['amount']
    srg_total_pto_hours = vp_total_pto_hours['amount'] + mgr_total_pto_hours['amount'] + c_total_pto_hours['amount']
    srg_total_billable_hours = vp_total_billable_hours['amount'] + mgr_total_billable_hours[
        'amount'] + c_total_billable_hours['amount']
    srg_total_hours = vp_total_hours['amount'] + mgr_total_hours['amount'] + c_total_hours[
        'amount']

    vp_loss_rev = vp_total_non_billable_hours['amount'] * 300
    smgr_lost_rev = smgr_total_non_billable_hours['amount'] * 250
    mgr_lost_rev = mgr_total_non_billable_hours['amount'] * 225
    c_lost_rev = c_total_non_billable_hours['amount'] * 200

    srg_total_lost_revenue = vp_loss_rev + mgr_lost_rev + c_lost_rev

    return vp_fixed_hours_by_employee, vp_hourly_hours_by_employee, vp_cgy_hours_by_employee, \
        vp_non_billable_hours_by_employee, vp_pto_hours_by_employee, vp_billable_hours_by_employee, \
        vp_total_hours_by_employee, vp_total_fixed_hours, vp_total_hourly_hours, vp_total_cgy_hours, \
        vp_total_non_billable_hours, vp_total_pto_hours, vp_total_billable_hours, vp_total_hours, \
        smgr_fixed_hours_by_employee, smgr_hourly_hours_by_employee, smgr_cgy_hours_by_employee, \
        smgr_non_billable_hours_by_employee, smgr_pto_hours_by_employee, smgr_billable_hours_by_employee, \
        smgr_total_hours_by_employee, smgr_total_fixed_hours, smgr_total_hourly_hours, smgr_total_cgy_hours, \
        smgr_total_non_billable_hours, smgr_total_pto_hours, smgr_total_billable_hours, smgr_total_hours, \
        mgr_fixed_hours_by_employee, mgr_hourly_hours_by_employee, mgr_cgy_hours_by_employee, \
        mgr_non_billable_hours_by_employee, mgr_pto_hours_by_employee, mgr_billable_hours_by_employee, \
        mgr_total_hours_by_employee, mgr_total_fixed_hours, mgr_total_hourly_hours, mgr_total_cgy_hours, \
        mgr_total_non_billable_hours, mgr_total_pto_hours, mgr_total_billable_hours, mgr_total_hours, \
        c_fixed_hours_by_employee, c_hourly_hours_by_employee, c_cgy_hours_by_employee, \
        c_non_billable_hours_by_employee, c_pto_hours_by_employee, c_billable_hours_by_employee, \
        c_total_hours_by_employee, c_total_fixed_hours, c_total_hourly_hours, c_total_cgy_hours, \
        c_total_non_billable_hours, c_total_pto_hours, c_total_billable_hours, c_total_hours, \
        srg_total_fixed_hours, srg_total_hourly_hours, srg_total_cgy_hours, \
        srg_total_non_billable_hours, srg_total_pto_hours, srg_total_billable_hours, srg_total_hours, \
        vp_loss_rev, smgr_lost_rev, mgr_lost_rev, c_lost_rev, srg_total_lost_revenue


def AdminDashboard(request):
    user_info = get_object_or_404(User, pk=request.user.id)
    employee_info = get_object_or_404(Employee, user=user_info.id)
    today = date.today()
    today_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    week_beg = today - timedelta(days=today.weekday())
    week_end = week_beg + timedelta(days=5)
    employees = Employee.objects.all().order_by('title', 'user__last_name')
    vps = employees.filter(title='VP')
    smgrs = employees.filter(title='SM')
    mgrs = employees.filter(title='M')
    consultants = employees.filter(Q(title='C') | Q(title='SC'))
    current_month = today.month

    if request.method == 'POST':
        month_form = MonthSelectForm(request.POST)
        if month_form.is_valid():
            selected_month = month_form.cleaned_data['month']
            new_data = getCompilationData(selected_month)
            if selected_month == 'YTD':
                pass
            else:
                selected_month = datetime.date(today.year, int(selected_month), 1)
            context = {'employee_info': employee_info, 'user_info': user_info, 'today': today, 'week_beg': week_beg,
                       'week_end': week_end, 'employees': employees, 'vps': vps,
                       'smgrs': smgrs, 'mgrs': mgrs, 'consultants': consultants,
                       'vp_fixed_hours_by_employee': new_data[0],
                       'vp_hourly_hours_by_employee': new_data[1],
                       'vp_cgy_hours_by_employee': new_data[2],
                       'vp_non_billable_hours_by_employee': new_data[3],
                       'vp_pto_hours_by_employee': new_data[4],
                       'vp_billable_hours_by_employee': new_data[5],
                       'vp_total_hours_by_employee': new_data[6],
                       'vp_total_fixed_hours': new_data[7],
                       'vp_total_hourly_hours': new_data[8],
                       'vp_total_cgy_hours': new_data[9],
                       'vp_total_non_billable_hours': new_data[10],
                       'vp_total_pto_hours': new_data[11],
                       'vp_total_billable_hours': new_data[12],
                       'vp_total_hours': new_data[13],
                       'smgr_fixed_hours_by_employee': new_data[14],
                       'smgr_hourly_hours_by_employee': new_data[15],
                       'smgr_cgy_hours_by_employee': new_data[16],
                       'smgr_non_billable_hours_by_employee': new_data[17],
                       'smgr_pto_hours_by_employee': new_data[18],
                       'smgr_billable_hours_by_employee': new_data[19],
                       'smgr_total_hours_by_employee': new_data[20],
                       'smgr_total_fixed_hours': new_data[21],
                       'smgr_total_hourly_hours': new_data[22],
                       'smgr_total_cgy_hours': new_data[23],
                       'smgr_total_non_billable_hours': new_data[24],
                       'smgr_total_pto_hours': new_data[25],
                       'smgr_total_billable_hours': new_data[26],
                       'smgr_total_hours': new_data[27],
                       'mgr_fixed_hours_by_employee': new_data[28],
                       'mgr_hourly_hours_by_employee': new_data[29],
                       'mgr_cgy_hours_by_employee': new_data[30],
                       'mgr_non_billable_hours_by_employee': new_data[31],
                       'mgr_pto_hours_by_employee': new_data[32],
                       'mgr_billable_hours_by_employee': new_data[33],
                       'mgr_total_hours_by_employee': new_data[34],
                       'mgr_total_fixed_hours': new_data[35],
                       'mgr_total_hourly_hours': new_data[36],
                       'mgr_total_cgy_hours': new_data[37],
                       'mgr_total_non_billable_hours': new_data[38],
                       'mgr_total_pto_hours': new_data[39],
                       'mgr_total_billable_hours': new_data[40],
                       'mgr_total_hours': new_data[41],
                       'c_fixed_hours_by_employee': new_data[42],
                       'c_hourly_hours_by_employee': new_data[43],
                       'c_cgy_hours_by_employee': new_data[44],
                       'c_non_billable_hours_by_employee': new_data[45],
                       'c_pto_hours_by_employee': new_data[46],
                       'c_billable_hours_by_employee': new_data[47],
                       'c_total_hours_by_employee': new_data[48],
                       'c_total_fixed_hours': new_data[49],
                       'c_total_hourly_hours': new_data[50],
                       'c_total_cgy_hours': new_data[51],
                       'c_total_non_billable_hours': new_data[52],
                       'c_total_pto_hours': new_data[53],
                       'c_total_billable_hours': new_data[54],
                       'c_total_hours': new_data[55],
                       'srg_total_fixed_hours': new_data[56],
                       'srg_total_hourly_hours': new_data[57],
                       'srg_total_cgy_hours': new_data[58],
                       'srg_total_non_billable_hours': new_data[59],
                       'srg_total_pto_hours': new_data[60],
                       'srg_total_billable_hours': new_data[61],
                       'srg_total_hours': new_data[62],
                       'vp_loss_rev': new_data[63],
                       'smgr_lost_rev': new_data[64],
                       'mgr_lost_rev': new_data[65],
                       'c_lost_rev': new_data[66],
                       'srg_total_lost_revenue': new_data[67],
                       'selected_month': selected_month,
                       'month_form': month_form}

            return render(request, 'adminDashboard.html', context)

    else:
        month_form = MonthSelectForm(initial={'month': current_month})
        current_month_data = getCompilationData(current_month)
        context = {'employee_info': employee_info, 'user_info': user_info, 'today': today, 'week_beg': week_beg,
                   'week_end': week_end, 'employees': employees, 'vps': vps,
                   'smgrs': smgrs, 'mgrs': mgrs, 'consultants': consultants,
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
                   'smgr_fixed_hours_by_employee': current_month_data[14],
                   'smgr_hourly_hours_by_employee': current_month_data[15],
                   'smgr_cgy_hours_by_employee': current_month_data[16],
                   'smgr_non_billable_hours_by_employee': current_month_data[17],
                   'smgr_pto_hours_by_employee': current_month_data[18],
                   'smgr_billable_hours_by_employee': current_month_data[19],
                   'smgr_total_hours_by_employee': current_month_data[20],
                   'smgr_total_fixed_hours': current_month_data[21],
                   'smgr_total_hourly_hours': current_month_data[22],
                   'smgr_total_cgy_hours': current_month_data[23],
                   'smgr_total_non_billable_hours': current_month_data[24],
                   'smgr_total_pto_hours': current_month_data[25],
                   'smgr_total_billable_hours': current_month_data[26],
                   'smgr_total_hours': current_month_data[27],
                   'mgr_fixed_hours_by_employee': current_month_data[28],
                   'mgr_hourly_hours_by_employee': current_month_data[29],
                   'mgr_cgy_hours_by_employee': current_month_data[30],
                   'mgr_non_billable_hours_by_employee': current_month_data[31],
                   'mgr_pto_hours_by_employee': current_month_data[32],
                   'mgr_billable_hours_by_employee': current_month_data[33],
                   'mgr_total_hours_by_employee': current_month_data[34],
                   'mgr_total_fixed_hours': current_month_data[35],
                   'mgr_total_hourly_hours': current_month_data[36],
                   'mgr_total_cgy_hours': current_month_data[37],
                   'mgr_total_non_billable_hours': current_month_data[38],
                   'mgr_total_pto_hours': current_month_data[39],
                   'mgr_total_billable_hours': current_month_data[40],
                   'mgr_total_hours': current_month_data[41],
                   'c_fixed_hours_by_employee': current_month_data[42],
                   'c_hourly_hours_by_employee': current_month_data[43],
                   'c_cgy_hours_by_employee': current_month_data[44],
                   'c_non_billable_hours_by_employee': current_month_data[45],
                   'c_pto_hours_by_employee': current_month_data[46],
                   'c_billable_hours_by_employee': current_month_data[47],
                   'c_total_hours_by_employee': current_month_data[48],
                   'c_total_fixed_hours': current_month_data[49],
                   'c_total_hourly_hours': current_month_data[50],
                   'c_total_cgy_hours': current_month_data[51],
                   'c_total_non_billable_hours': current_month_data[52],
                   'c_total_pto_hours': current_month_data[53],
                   'c_total_billable_hours': current_month_data[54],
                   'c_total_hours': current_month_data[55],
                   'srg_total_fixed_hours': current_month_data[56],
                   'srg_total_hourly_hours': current_month_data[57],
                   'srg_total_cgy_hours': current_month_data[58],
                   'srg_total_non_billable_hours': current_month_data[59],
                   'srg_total_pto_hours': current_month_data[60],
                   'srg_total_billable_hours': current_month_data[61],
                   'srg_total_hours': current_month_data[62],
                   'vp_loss_rev': current_month_data[63],
                   'smgr_lost_rev': current_month_data[64],
                   'mgr_lost_rev': current_month_data[65],
                   'c_lost_rev': current_month_data[66],
                   'srg_total_lost_revenue': current_month_data[67],
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

            return redirect('engagement-dashboard')
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

    queryset = Time.objects.values('ts_date',
                                   'employee__user__username',
                                   'engagement__engagement_srg_id',
                                   'engagement__parent__parent_name',
                                   'engagement__provider',
                                   'engagement__provider__provider_name',
                                   'engagement__time_code',
                                   'engagement__time_code__time_code_desc',
                                   'engagement__fye',
                                   'engagement__type_id',
                                   'engagement__is_rac',
                                   'engagement__engagement_hourly_rate',
                                   'hours',
                                   'note').order_by('ts_date', 'engagement__parent__parent_name',
                                                    'engagement__provider',
                                                    'engagement__fye')

    expense_queryset = Expense.objects.values('ts_date', 'employee__user__username', 'engagement__engagement_srg_id',
                                              'expense_category', 'expense_amount').order_by('ts_date')

    f = TimesheetFilter(request.GET, queryset=queryset)
    expense_filter = ExpenseFilter(request.GET, queryset=expense_queryset)

    if request.method == 'GET' and 'extract_button' in request.GET:
        ts_data = read_frame(f.qs)

        ex_data = read_frame(expense_filter.qs)

        fname = 'EmployeeTimesheetCompilation'

        response = HttpResponse(content_type='application/vns.ms-excel')
        response['Content-Disposition'] = 'attachment; filename=' + fname + '.xlsx'
        with pandas.ExcelWriter(response, engine='xlsxwriter') as writer:
            ts_data.to_excel(writer, sheet_name='SRG Timesheet Compilation', index=False, header=True)
            ex_data.to_excel(writer, sheet_name='SRG Expense Compilation', index=False, header=True)
            # df_hfy.to_excel(writer, sheet_name=('PFY ' + fye), index=False, header=True)

            return response

    context = {'filter': f, 'expense_filter': expense_filter, 'today': today, 'week_beg': week_beg,
               'week_end': week_end, 'user_info': user_info}
    return render(request, 'adminTimesheet.html', context)


def getStaffWeekHours(per_beg, per_end):
    data = Todolist.objects.values('employee__user__username').filter(todo_date__gte=per_beg).filter(
        todo_date__lte=per_end).annotate(
        total_hours_sum=Coalesce(Sum('anticipated_hours'), 0, output_field=DecimalField()
                                 ),
        non_billable_hours_sum=Coalesce(
            Sum(Case(When(engagement__type_id='N', then=F('anticipated_hours')))), 0,
            output_field=DecimalField()),
        billable_hours_sum=Coalesce(
            Sum(
                Case(
                    When(
                        Q(engagement__type_id='H') | Q(engagement__type_id='F') | Q(engagement__type_id='C'),
                        then=F('anticipated_hours')
                    )
                )
            ), 0, output_field=DecimalField()
        )
    )
    return data


def getStaffNotInTodoList(per_beg, per_end):
    data = Todolist.objects.values('employee__user__username').filter(todo_date__gte=per_beg).filter(
        todo_date__lte=per_end)

    data_none = Employee.objects.exclude(user__username__in=data)

    return data_none


def AdminPlanning(request):
    user_info = get_object_or_404(User, pk=request.user.id)
    period_beg = date.today()
    today = date.today()
    week_beg = today - timedelta(days=today.weekday()) - timedelta(days=1)
    week_end = week_beg + timedelta(days=6)
    period_days = []
    for i in range(180):
        period_days.append(period_beg + timedelta(days=i))
    employees = Employee.objects.values('user__username')
    todolists = Todolist.objects.values('employee__user__username', 'engagement__provider',
                                        'engagement__provider__provider_name', 'todo_date',
                                        'engagement__engagement_srg_id', 'anticipated_hours').order_by('todo_date',
                                                                                                       'employee__user__username')

    current_employees = User.objects.values('username')

    current_week_hours = getStaffWeekHours(week_beg, week_end)
    current_week_no_hours = getStaffNotInTodoList(week_beg, week_end)

    next_week_beg = week_beg + timedelta(days=7)
    next_week_end = week_end + timedelta(days=7)

    next_week_hours = getStaffWeekHours(next_week_beg, next_week_end)
    next_week_no_hours = getStaffNotInTodoList(next_week_beg, next_week_end)

    two_week_beg = next_week_beg + timedelta(days=7)
    two_week_end = next_week_end + timedelta(days=7)

    two_week_hours = getStaffWeekHours(two_week_beg, two_week_end)
    two_week_no_hours = getStaffNotInTodoList(two_week_beg, two_week_end)

    three_week_beg = two_week_beg + timedelta(days=7)
    three_week_end = two_week_end + timedelta(days=7)

    three_week_hours = getStaffWeekHours(three_week_beg, three_week_end)
    three_week_no_hours = getStaffNotInTodoList(three_week_beg, three_week_end)

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
               'current_week_no_hours': current_week_no_hours,
               'current_week_hours': current_week_hours,
               'next_week_beg': next_week_beg, 'next_week_end': next_week_end,
               'next_week_no_hours': next_week_no_hours,
               'next_week_hours': next_week_hours,
               'two_week_beg': two_week_beg,
               'two_week_end': two_week_end,
               'two_week_no_hours': two_week_no_hours,
               'two_week_hours': two_week_hours,
               'three_week_beg': three_week_beg,
               'three_week_end': three_week_end,
               'three_week_no_hours': three_week_no_hours,
               'three_week_hours': three_week_hours,
               'current_employees': current_employees, 'today': today, 'user_info': user_info
               }
    return render(request, 'adminPlanning.html', context)


def AdminEmployeeDashboard(request, pk, per_beg, per_end):
    user_info = get_object_or_404(User, pk=request.user.id)
    today = date.today()
    per_beg_object = datetime.datetime.strptime(per_beg, "%Y-%m-%d")
    per_end_object = datetime.datetime.strptime(per_end, "%Y-%m-%d")

    timesheet_entries = Time.objects.all().filter(employee__user__username=user_info.username).filter(
        date__gte=per_beg).filter(date__lte=per_end)

    billable_hours_sum = timesheet_entries.exclude(Q(engagement__type_id='N') | Q(time_type_id_id='N')).aggregate(
        amount=Coalesce(Sum('hours'), 0, output_field=DecimalField(0.00)))

    non_billable_hours_sum = timesheet_entries.filter(Q(engagement__type_id='N') | Q(time_type_id_id='N')).aggregate(
        amount=Coalesce(Sum('hours'), 0, output_field=DecimalField(0.00)))

    employee_td_entries_all = Todolist.objects.values('todo_date',
                                                      'engagement__parent_id',
                                                      'engagement__parent_id__parent_name',
                                                      'engagement__provider_id',
                                                      'engagement__provider_id__provider_name',
                                                      'engagement__time_code',
                                                      'engagement__time_code__time_code_desc').filter(
        employee__user__username=request.user.username).order_by('todo_date').annotate(
        hsum=Sum('anticipated_hours'))

    employee_td_entries = employee_td_entries_all.filter(todo_date=today).order_by('todo_date')

    context = {'per_end_object': per_end_object, 'per_beg_object': per_beg_object, 'user_info': user_info,
               'timesheet_entries': timesheet_entries, 'today': today,
               'billable_hours_sum': billable_hours_sum, 'non_billable_hours_sum': non_billable_hours_sum,
               'employee_td_entries': employee_td_entries, 'employee_td_entries_all': employee_td_entries_all}
    return render(request, 'adminEmployeeDashboard.html', context)


def EmployeeTimesheetReview(request):
    user_info = get_object_or_404(User, pk=request.user.id)
    last_week_beg = date.today() - timedelta(days=7) - timedelta(days=date.today().weekday()) - timedelta(days=1)
    last_week_end = last_week_beg + timedelta(days=6)

    current_week = []
    current_week_ts = {}

    for i in range(7):
        current_week.append(last_week_beg + timedelta(days=i))

    employee_ts_entries = Time.objects.filter(employee__user__username=request.user.username).filter(
        ts_date__gte=last_week_beg).filter(ts_date__lte=last_week_end).order_by('ts_date')

    user_engagements = Engagement.objects.select_related().filter(
        assignments__employee__employee_id=user_info.employee.employee_id)

    employee_hours_by_day = employee_ts_entries.values('ts_date').annotate(ts_hours=Sum('hours'))

    total_weekly_hours = employee_ts_entries.aggregate(hours_sum=Coalesce(Sum('hours'), 0, output_field=DecimalField()))

    total_available_hours = 40 - total_weekly_hours['hours_sum']

    if request.method == 'POST':
        if 'submit_button' in request.POST:
            employee_instance = get_object_or_404(Employee, user=request.user.id)
            employee_instance.ts_is_submitted = True
            employee_instance.save()
            return redirect('dashboard')
        if 'time_button' in request.POST:
            time_form = TimeForm(request.POST)
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

                return redirect('employee-timesheet-review')
        elif 'expense_button' in request.POST:
            expense_form = ExpenseForm()
            if expense_form.is_valid():
                employee_instance = get_object_or_404(Employee, user=request.user.id)
                engagement_id = request.POST.get('expense-input')
                engagement_instance = get_object_or_404(Engagement, engagement_srg_id=engagement_id)

                new_expense = expense_form.save(commit=False)
                new_expense.employee = employee_instance
                new_expense.engagement = engagement_instance

                new_expense.save()

                return redirect('employee-timesheet')
        else:
            expense_form = ExpenseForm()
            time_form = TimeForm()
    else:
        time_form = TimeForm()
        expense_form = ExpenseForm()

    context = {'user_info': user_info, 'last_week_beg': last_week_beg, 'last_week_end': last_week_end,
               'current_week': current_week, 'employee_ts_entries': employee_ts_entries,
               'employee_hours_by_day': employee_hours_by_day,
               'user_engagements': user_engagements, 'total_weekly_hours': total_weekly_hours,
               'time_form': time_form, 'total_available_hours': total_available_hours}

    return render(request, 'employeeTimesheetReview.html', context)


def EmployeeTimesheet(request):
    user_info = get_object_or_404(User, pk=request.user.id)
    today = date.today()
    week_beg = today - timedelta(days=today.weekday()) - timedelta(days=1)
    week_end = week_beg + timedelta(days=6)
    # user_engagements = user_assignments.filter(employee_id=request.user.employee.employee_id)

    # user_assignments = Assignments.objects.filter(employee_id=user_info.employee.employee_id).values(
    # 'engagement_id') user_engagements = Engagement.objects.filter(engagement_id__in=user_assignments).order_by(
    # '-fye', 'time_code', 'parent_id')

    user_engagements = Engagement.objects.select_related().filter(
        assignments__employee__employee_id=user_info.employee.employee_id)
    # user_engagements = user_engagements.filter(assignments__employee__employee_id=user_info.employee.employee_id)

    employee_ts_entries = Time.objects.filter(employee__user__username=request.user.username).filter(
        ts_date__gte=week_beg).filter(ts_date__lte=week_end).order_by('ts_date')

    employee_hours_by_day = employee_ts_entries.values('ts_date').annotate(ts_hours=Sum('hours'))

    total_weekly_hours = employee_ts_entries.aggregate(hours_sum=Coalesce(Sum('hours'), 0, output_field=DecimalField()))

    total_available_hours = 40 - total_weekly_hours['hours_sum']

    current_week = []
    current_week_ts = {}

    for i in range(7):
        current_week.append(week_beg + timedelta(days=i))

    if request.method == 'POST':
        if 'time_button' in request.POST:
            time_form = TimeForm(request.POST)
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
        elif 'expense_button' in request.POST:
            expense_form = ExpenseForm()
            if expense_form.is_valid():
                employee_instance = get_object_or_404(Employee, user=request.user.id)
                engagement_id = request.POST.get('expense-input')
                engagement_instance = get_object_or_404(Engagement, engagement_srg_id=engagement_id)

                new_expense = expense_form.save(commit=False)
                new_expense.employee = employee_instance
                new_expense.engagement = engagement_instance

                new_expense.save()

                return redirect('employee-timesheet')
        else:
            expense_form = ExpenseForm()
            time_form = TimeForm()
    else:
        time_form = TimeForm()
        expense_form = ExpenseForm()

    context = {'today': today, 'employee_ts_entries': employee_ts_entries, 'week_beg': week_beg, 'week_end': week_end,
               'current_week': current_week, 'current_week_ts': current_week_ts, 'user_engagements': user_engagements,
               'time_form': time_form, 'expense_form': expense_form,
               'total_weekly_hours': total_weekly_hours, 'user_info': user_info,
               'total_available_hours': total_available_hours,
               'employee_hours_by_day': employee_hours_by_day}

    return render(request, 'employeeTimesheet.html', context)


def EmployeeTodolist(request):
    user_info = get_object_or_404(User, pk=request.user.id)
    today = date.today()
    week_beg = today - timedelta(days=today.weekday()) - timedelta(days=1)
    week_end = week_beg + timedelta(days=5)
    # user_assignments = Assignments.objects.filter(employee_id=user_info.employee.employee_id).values('engagement_id')
    # user_engagements = Engagement.objects.filter(engagement_id__in=user_assignments)
    user_engagements = Engagement.objects.select_related().filter(
        assignments__employee__employee_id=user_info.employee.employee_id)

    employee_td_entries = Todolist.objects.select_related('engagement').filter(
        employee__user__username=user_info.username).filter(
        todo_date__gte=week_beg).order_by('todo_date')

    employee_td_hours_by_day = employee_td_entries.values('todo_date').annotate(
        total_day_td_hours=Sum('anticipated_hours'))

    current_week = []
    current_week_ts = {}

    for i in range(20):
        current_week.append(week_beg + timedelta(days=i))

    paginator = Paginator(current_week, 7)

    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    if request.method == 'POST':
        todo_form = TodoForm(request.POST)
        if todo_form.is_valid():

            engagement_id = request.POST.get('todo-input')
            engagement_instance = get_object_or_404(Engagement, engagement_srg_id=engagement_id)
            employee_instance = get_object_or_404(Employee, user=request.user.id)

            start_date = request.POST.get('todo_date')
            start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d")
            end_date = request.POST.get('todo_date_end')
            if end_date == '':
                end_date = start_date
            else:
                end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d")

            number_of_days = end_date - start_date

            if number_of_days.days == 0:
                new_entry = todo_form.save(commit=False)
                new_entry.employee_id = employee_instance.employee_id
                new_entry.engagement = engagement_instance
                new_entry.save()
            else:
                number_of_days = number_of_days + timedelta(days=1)
                for i in range(0, number_of_days.days):
                    new_entry = Todolist(
                        employee=employee_instance,
                        engagement=engagement_instance,
                        todo_date=start_date + timedelta(days=i),
                        todo_date_end=start_date + timedelta(days=1),
                        anticipated_hours=request.POST.get('anticipated_hours'),
                        note=request.POST.get('note')
                    )
                    # new_entry.todo_date = start_date + timedelta(days=i)
                    # new_entry.todo_date_end = start_date + timedelta(days=i)
                    # new_entry.employee_id = employee_instance.employee_id
                    # new_entry.engagement = engagement_instance
                    new_entry.save()

            return redirect('employee-todolist')
    else:
        todo_form = TodoForm()

    context = {'employee_td_entries': employee_td_entries, 'week_beg': week_beg, 'week_end': week_end, 'today': today,
               'todo_form': todo_form, 'user_info': user_info, 'page_obj': page_obj, 'paginator': paginator,
               'employee_td_hours_by_day': employee_td_hours_by_day,
               'current_week': current_week, 'current_week_ts': current_week_ts, 'user_engagements': user_engagements}

    return render(request, 'employeeTodolist.html', context)


def EmployeeExpense(request):
    user_info = get_object_or_404(User, pk=request.user.id)
    today = date.today()
    week_beg = today - timedelta(days=today.weekday()) - timedelta(days=1)
    week_end = week_beg + timedelta(days=6)

    current_employee = get_object_or_404(Employee, user_id=request.user.id)
    employee_expenses = Expense.objects.filter(employee__user__username=request.user.username).filter(
        date__gte=week_beg).filter(date__lte=week_end).order_by('date')

    total_expense = employee_expenses.aggregate(Sum('expense_amount'))

    context = {'employee_expenses': employee_expenses, 'week_beg': week_beg, 'week_end': week_end,
               'total_expense': total_expense, 'user_info': user_info}

    return render(request, 'employeeExpense.html', context)


def ExtractEngagementTimesheet(request, pk):
    engagement_instance = get_object_or_404(Engagement, pk=pk)

    queryset = Time.objects.filter(engagement=engagement_instance.engagement_id).values('ts_date',
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


def createEmployeeHoursCompilationReport(request, mnth):
    global period
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Justify', alignment=TA_JUSTIFY))
    title = Paragraph('<para>Strategic Reimbursement Group, LLC</para>', styles['Normal'])
    subTitle = Paragraph('<para>Employee Hours Compilation Report</para>', styles['Normal'])
    if mnth == "YTD":
        period_text = Paragraph('<para>Year To Date</para>', styles['Normal'])
        period = "YTD"
    else:
        period_date = datetime.datetime.strptime(mnth, "%Y-%m-%d")
        period_text = Paragraph('<para>' + str(period_date.strftime("%B")) + " " + str(period_date.year) + '</para>')
        period = period_date.month
        print(period)
    vps = Employee.objects.filter(title='VP').values('employee_id', 'user__username')
    smgrs = Employee.objects.filter(title='SM').values('employee_id', 'user__username')
    mgrs = Employee.objects.filter(title='M').values('employee_id', 'user__username')
    cs = Employee.objects.filter(Q(title='SC') | Q(title='C')).values('employee_id', 'user__username')

    elements = []

    # Create Column Headers for Table #
    employeeHeader = Paragraph('<para align=center>Employee</para>', styles['Normal'])
    fixedHeader = Paragraph('<para align=center>Fixed</para>', styles['Normal'])
    hourlyHeader = Paragraph('<para align=center>Hourly</para>', styles['Normal'])
    cgyHeader = Paragraph('<para align=center>CGY</para>', styles['Normal'])
    nbHeader = Paragraph('<para align=center>NB</para>', styles['Normal'])
    ptoHeader = Paragraph('<para align=center>PTO</para>', styles['Normal'])
    billableHeader = Paragraph('<para align=center>Total Billable</para>', styles['Normal'])
    totalHeader = Paragraph('<para align=center>Total</para>', styles['Normal'])
    percentBillableHeader = Paragraph('<para align=center>% Billable</para>', styles['Normal'])

    data = [[employeeHeader, fixedHeader, hourlyHeader, cgyHeader, nbHeader, ptoHeader, billableHeader, totalHeader,
             percentBillableHeader]]

    compilationData = getCompilationData(period)

    vp_fixed = compilationData[0]
    vp_hourly = compilationData[1]
    vp_cgy = compilationData[2]
    vp_nb = compilationData[3]
    vp_pto = compilationData[4]
    vp_billable = compilationData[5]
    vp_total = compilationData[6]

    employeeHourlyColumn = 0
    employeeFixedColumn = 0
    employeeCGYColumn = 0
    employeeNBColumn = 0
    employeePTOColumn = 0
    employeeBillableColumn = 0
    employeeTotalColumn = 0
    percentBillable = 0

    for emp in vps:
        employeeColumn = Paragraph('<para align=left>' + str(emp['user__username']) + '</para>', styles['Normal'])
        for item in vp_fixed:
            if item['employee_id'] == emp['employee_id']:
                employeeFixedColumn = str(item['fixed_hours_by_employee_sum'])
                data.append(employeeFixedColumn)
        for item in vp_hourly:
            if item['employee_id'] == emp['employee_id']:
                employeeHourlyColumn = Paragraph(
                    '<para align=center>' + str(item['hourly_hours_by_employee_sum']) + '</para>', styles['Normal'])
                # data.append([employeeHourlyColumn])
        for item in vp_cgy:
            if item['employee_id'] == emp['employee_id']:
                employeeCGYColumn = Paragraph(
                    '<para align=center>' + str(item['cgy_hours_by_employee_sum']) + '</para>', styles['Normal'])
        for item in vp_nb:
            if item['employee_id'] == emp['employee_id']:
                employeeNBColumn = Paragraph('<para align=center>' + str(item['nb_hours_by_employee_sum']) + '</para>',
                                             styles['Normal'])
        for item in vp_pto:
            if item['employee_id'] == emp['employee_id']:
                employeePTOColumn = Paragraph(
                    '<para align=center>' + str(item['pto_hours_by_employee_sum']) + '</para>', styles['Normal'])
        for item in vp_billable:
            if item['employee_id'] == emp['employee_id']:
                percentBillable = (item['billable_hours_sum'] / 200) * 100
                employeeBillableColumn = Paragraph('<para align=center>' + str(item['billable_hours_sum']) + '</para>',
                                                   styles['Normal'])
        for item in vp_total:
            if item['employee_id'] == emp['employee_id']:
                employeeTotalColumn = Paragraph('<para align=center>' + str(item['total_hours_sum']) + '</para>',
                                                styles['Normal'])

        employeePercentBillableColumn = Paragraph('<para align=center>' + str(percentBillable) + ' %</para>',
                                                  styles['Normal'])

        data.append([employeeColumn, employeeFixedColumn, employeeHourlyColumn, employeeCGYColumn, employeeNBColumn,
                     employeePTOColumn, employeeBillableColumn, employeeTotalColumn, employeePercentBillableColumn])

    vp_total_data = []

    vp_total_text = Paragraph('<para align=center color=white>VP Total:</para>')
    vp_fixed_total_column = Paragraph('<para align=center color=white>' + str(compilationData[7]['amount']) + '</para>')
    vp_hourly_total = Paragraph('<para align=center color=white>' + str(compilationData[8]['amount']) + '</para>')
    vp_cgy_total = Paragraph('<para align=center color=white>' + str(compilationData[9]['amount']) + '</para>')
    vp_nb_total = Paragraph('<para align=center color=white>' + str(compilationData[10]['amount']) + '</para>')
    vp_pto_total = Paragraph('<para align=center color=white>' + str(compilationData[11]['amount']) + '</para>')
    vp_billable_total = Paragraph('<para align=center color=white>' + str(compilationData[12]['amount']) + '</para>')
    vp_total_total = Paragraph('<para align=center color=white>' + str(compilationData[13]['amount']) + '</para>')
    vp_percent_billable_total = Paragraph(
        '<para align=center color=white>' + str(compilationData[12]['amount'] / 200 * 100) + ' %</para>')

    vp_total_data.append(
        [vp_total_text, vp_fixed_total_column, vp_hourly_total, vp_cgy_total, vp_nb_total, vp_pto_total,
         vp_billable_total, vp_total_total, vp_percent_billable_total])
    # ################################################# SR MANAGERS TABLE ##############################################
    smgr_fixed = compilationData[14]
    smgr_hourly = compilationData[15]
    smgr_cgy = compilationData[16]
    smgr_nb = compilationData[17]
    smgr_pto = compilationData[18]
    smgr_billable = compilationData[19]
    smgr_total = compilationData[20]

    smgrEmployeeFixedColumn = 0
    smgrEmployeeHourlyColumn = 0
    smgrEmployeeCGYColumn = 0
    smgrEmployeeNBColumn = 0
    smgrEmployeePTOColumn = 0
    smgrEmployeeBillableColumn = 0
    smgrEmployeeTotalColumn = 0
    smgrPercentBillable = 0

    smgr_data = []
    smgr_total_data = []

    smgr_total_text = Paragraph('<para align=center color=white>Sr. Manager Total:</para>')
    smgr_fixed_total_column = Paragraph(
        '<para align=center color=white>' + str(compilationData[35]['amount']) + '</para>')
    smgr_hourly_total = Paragraph('<para align=center color=white>' + str(compilationData[21]['amount']) + '</para>')
    smgr_cgy_total = Paragraph('<para align=center color=white>' + str(compilationData[22]['amount']) + '</para>')
    smgr_nb_total = Paragraph('<para align=center color=white>' + str(compilationData[23]['amount']) + '</para>')
    smgr_pto_total = Paragraph('<para align=center color=white>' + str(compilationData[24]['amount']) + '</para>')
    smgr_billable_total = Paragraph('<para align=center color=white>' + str(compilationData[25]['amount']) + '</para>')
    smgr_total_total = Paragraph('<para align=center color=white>' + str(compilationData[26]['amount']) + '</para>')
    smgr_percent_billable_total = Paragraph(
        '<para align=center color=white>' + str(compilationData[25]['amount'] / 200 * 100) + ' %</para>')

    smgr_total_data.append(
        [smgr_total_text, smgr_fixed_total_column, smgr_hourly_total, smgr_cgy_total, smgr_nb_total, smgr_pto_total,
         smgr_billable_total, smgr_total_total, smgr_percent_billable_total])

    for emp in smgrs:
        employeeColumn = Paragraph('<para align=left>' + str(emp['user__username']) + '</para>', styles['Normal'])
        for item in smgr_fixed:
            if item['employee_id'] == emp['employee_id']:
                smgrEmployeeFixedColumn = str(item['fixed_hours_by_employee_sum'])
        for item in smgr_hourly:
            if item['employee_id'] == emp['employee_id']:
                smgrEmployeeHourlyColumn = Paragraph(
                    '<para align=center>' + str(item['hourly_hours_by_employee_sum']) + '</para>', styles['Normal'])
                # data.append([employeeHourlyColumn])
        for item in smgr_cgy:
            if item['employee_id'] == emp['employee_id']:
                smgrEmployeeCGYColumn = Paragraph(
                    '<para align=center>' + str(item['cgy_hours_by_employee_sum']) + '</para>')
        for item in smgr_nb:
            if item['employee_id'] == emp['employee_id']:
                smgrEmployeeNBColumn = Paragraph(
                    '<para align=center>' + str(item['non_billable_hours_sum']) + '</para>', styles['Normal'])
        for item in smgr_pto:
            if item['employee_id'] == emp['employee_id']:
                smgrEmployeePTOColumn = Paragraph(
                    '<para align=center>' + str(item['pto_hours_by_employee_sum']) + '</para>', styles['Normal'])
        for item in smgr_billable:
            if item['employee_id'] == emp['employee_id']:
                smgrPercentBillable = (item['billable_hours_sum'] / 200) * 100
                smgrEmployeeBillableColumn = Paragraph(
                    '<para align=center>' + str(item['billable_hours_sum']) + '</para>', styles['Normal'])
        for item in smgr_total:
            if item['employee_id'] == emp['employee_id']:
                smgrEmployeeTotalColumn = Paragraph(
                    '<para align=center>' + str(item['total_hours_sum']) + '</para>', styles['Normal'])
        smgrEmployeePercentBillableColumn = Paragraph('<para align=center>' + str(smgrPercentBillable) + ' %</para>',
                                                      styles['Normal'])

        smgr_data.append([employeeColumn, smgrEmployeeFixedColumn, smgrEmployeeHourlyColumn, smgrEmployeeCGYColumn,
                          smgrEmployeeNBColumn, smgrEmployeePTOColumn, smgrEmployeeBillableColumn,
                          smgrEmployeeTotalColumn, smgrEmployeePercentBillableColumn])

    # ################################################# MANAGERS TABLE #################################################
    mgr_fixed = compilationData[28]
    mgr_hourly = compilationData[29]
    mgr_cgy = compilationData[30]
    mgr_nb = compilationData[31]
    mgr_pto = compilationData[32]
    mgr_billable = compilationData[33]
    mgr_total = compilationData[34]

    mgrEmployeeFixedColumn = 0
    mgrEmployeeHourlyColumn = 0
    mgrEmployeeCGYColumn = 0
    mgrEmployeeNBColumn = 0
    mgrEmployeePTOColumn = 0
    mgrEmployeeBillableColumn = 0
    mgrEmployeeTotalColumn = 0
    mgrPercentBillable = 0

    mgr_data = []
    mgr_total_data = []

    mgr_total_text = Paragraph('<para align=center color=white>Manager Total:</para>')
    mgr_fixed_total_column = Paragraph(
        '<para align=center color=white>' + str(compilationData[35]['amount']) + '</para>')
    mgr_hourly_total = Paragraph('<para align=center color=white>' + str(compilationData[36]['amount']) + '</para>')
    mgr_cgy_total = Paragraph('<para align=center color=white>' + str(compilationData[37]['amount']) + '</para>')
    mgr_nb_total = Paragraph('<para align=center color=white>' + str(compilationData[38]['amount']) + '</para>')
    mgr_pto_total = Paragraph('<para align=center color=white>' + str(compilationData[39]['amount']) + '</para>')
    mgr_billable_total = Paragraph('<para align=center color=white>' + str(compilationData[40]['amount']) + '</para>')
    mgr_total_total = Paragraph('<para align=center color=white>' + str(compilationData[41]['amount']) + '</para>')
    mgr_percent_billable_total = Paragraph(
        '<para align=center color=white>' + str(compilationData[40]['amount'] / 200 * 100) + ' %</para>')

    mgr_total_data.append(
        [mgr_total_text, mgr_fixed_total_column, mgr_hourly_total, mgr_cgy_total, mgr_nb_total, mgr_pto_total,
         mgr_billable_total, mgr_total_total, mgr_percent_billable_total])

    for emp in mgrs:
        employeeColumn = Paragraph('<para align=left>' + str(emp['user__username']) + '</para>', styles['Normal'])
        for item in mgr_fixed:
            if item['employee_id'] == emp['employee_id']:
                mgrEmployeeFixedColumn = str(item['fixed_hours_by_employee_sum'])
        for item in mgr_hourly:
            if item['employee_id'] == emp['employee_id']:
                mgrEmployeeHourlyColumn = Paragraph(
                    '<para align=center>' + str(item['hourly_hours_by_employee_sum']) + '</para>', styles['Normal'])
                # data.append([employeeHourlyColumn])
        for item in mgr_cgy:
            if item['employee_id'] == emp['employee_id']:
                mgrEmployeeCGYColumn = Paragraph(
                    '<para align=center>' + str(item['cgy_hours_by_employee_sum']) + '</para>')
        for item in mgr_nb:
            if item['employee_id'] == emp['employee_id']:
                mgrEmployeeNBColumn = Paragraph(
                    '<para align=center>' + str(item['non_billable_hours_sum']) + '</para>', styles['Normal'])
        for item in mgr_pto:
            if item['employee_id'] == emp['employee_id']:
                mgrEmployeePTOColumn = Paragraph(
                    '<para align=center>' + str(item['pto_hours_by_employee_sum']) + '</para>', styles['Normal'])
        for item in mgr_billable:
            if item['employee_id'] == emp['employee_id']:
                mgrPercentBillable = (item['billable_hours_sum'] / 200) * 100
                mgrEmployeeBillableColumn = Paragraph(
                    '<para align=center>' + str(item['billable_hours_sum']) + '</para>', styles['Normal'])
        for item in mgr_total:
            if item['employee_id'] == emp['employee_id']:
                mgrEmployeeTotalColumn = Paragraph(
                    '<para align=center>' + str(item['total_hours_sum']) + '</para>', styles['Normal'])
        mgrEmployeePercentBillableColumn = Paragraph('<para align=center>' + str(mgrPercentBillable) + ' %</para>',
                                                     styles['Normal'])

        mgr_data.append([employeeColumn, mgrEmployeeFixedColumn, mgrEmployeeHourlyColumn, mgrEmployeeCGYColumn,
                         mgrEmployeeNBColumn, mgrEmployeePTOColumn, mgrEmployeeBillableColumn,
                         mgrEmployeeTotalColumn, mgrEmployeePercentBillableColumn])

    # ##################################### CONSULTANT TABLE ######################################################
    c_fixed = compilationData[42]
    c_hourly = compilationData[43]
    c_cgy = compilationData[44]
    c_nb = compilationData[45]
    c_pto = compilationData[46]
    c_billable = compilationData[47]
    c_total = compilationData[48]

    cEmployeeFixedColumn = 0
    cEmployeeHourlyColumn = 0
    cEmployeeCGYColumn = 0
    cEmployeeNBColumn = 0
    cEmployeePTOColumn = 0
    cEmployeeBillableColumn = 0
    cEmployeeTotalColumn = 0
    cPercentBillable = 0

    c_data = []
    c_total_data = []

    c_total_text = Paragraph('<para align=center color=white>Consultant Total:</para>')
    c_fixed_total_column = Paragraph(
        '<para align=center color=white>' + str(compilationData[49]['amount']) + '</para>')
    c_hourly_total = Paragraph('<para align=center color=white>' + str(compilationData[50]['amount']) + '</para>')
    c_cgy_total = Paragraph('<para align=center color=white>' + str(compilationData[51]['amount']) + '</para>')
    c_nb_total = Paragraph('<para align=center color=white>' + str(compilationData[52]['amount']) + '</para>')
    c_pto_total = Paragraph('<para align=center color=white>' + str(compilationData[53]['amount']) + '</para>')
    c_billable_total = Paragraph('<para align=center color=white>' + str(compilationData[54]['amount']) + '</para>')
    c_total_total = Paragraph('<para align=center color=white>' + str(compilationData[55]['amount']) + '</para>')
    c_percent_billable_total = Paragraph(
        '<para align=center color=white>' + str(compilationData[54]['amount'] / 200 * 100) + ' %</para>')

    c_total_data.append(
        [c_total_text, c_fixed_total_column, c_hourly_total, c_cgy_total, c_nb_total, c_pto_total,
         c_billable_total, c_total_total, c_percent_billable_total])

    for emp in cs:
        employeeColumn = Paragraph('<para align=left>' + str(emp['user__username']) + '</para>', styles['Normal'])
        for item in c_fixed:
            if item['employee_id'] == emp['employee_id']:
                cEmployeeFixedColumn = str(item['fixed_hours_by_employee_sum'])
        for item in c_hourly:
            if item['employee_id'] == emp['employee_id']:
                cEmployeeHourlyColumn = Paragraph(
                    '<para align=center>' + str(item['hourly_hours_by_employee_sum']) + '</para>', styles['Normal'])
                # data.append([employeeHourlyColumn])
        for item in c_cgy:
            if item['employee_id'] == emp['employee_id']:
                cEmployeeCGYColumn = Paragraph(
                    '<para align=center>' + str(item['cgy_hours_by_employee_sum']) + '</para>')
        for item in c_nb:
            if item['employee_id'] == emp['employee_id']:
                cEmployeeNBColumn = Paragraph(
                    '<para align=center>' + str(item['non_billable_hours_sum']) + '</para>', styles['Normal'])
        for item in c_pto:
            if item['employee_id'] == emp['employee_id']:
                cEmployeePTOColumn = Paragraph(
                    '<para align=center>' + str(item['pto_hours_by_employee_sum']) + '</para>', styles['Normal'])
        for item in c_billable:
            if item['employee_id'] == emp['employee_id']:
                cPercentBillable = (item['billable_hours_sum'] / 200) * 100
                cEmployeeBillableColumn = Paragraph(
                    '<para align=center>' + str(item['billable_hours_sum']) + '</para>', styles['Normal'])
        for item in c_total:
            if item['employee_id'] == emp['employee_id']:
                cEmployeeTotalColumn = Paragraph(
                    '<para align=center>' + str(item['total_hours_sum']) + '</para>', styles['Normal'])
        cEmployeePercentBillableColumn = Paragraph('<para align=center>' + str(cPercentBillable) + ' %</para>',
                                                   styles['Normal'])

        c_data.append([employeeColumn, cEmployeeFixedColumn, cEmployeeHourlyColumn, cEmployeeCGYColumn,
                       cEmployeeNBColumn, cEmployeePTOColumn, cEmployeeBillableColumn,
                       cEmployeeTotalColumn, cEmployeePercentBillableColumn])

    # ##################################### GRAND TOTAL CREATE ###################################################

    total_total_data = []

    total_total_text = Paragraph('<para align=center color=white>Grand Total:</para>')
    total_fixed_total_column = Paragraph(
        '<para align=center color=white>' + str(compilationData[56]) + '</para>')
    total_hourly_total = Paragraph('<para align=center color=white>' + str(compilationData[57]) + '</para>')
    total_cgy_total = Paragraph('<para align=center color=white>' + str(compilationData[58]) + '</para>')
    total_nb_total = Paragraph('<para align=center color=white>' + str(compilationData[59]) + '</para>')
    total_pto_total = Paragraph('<para align=center color=white>' + str(compilationData[60]) + '</para>')
    total_billable_total = Paragraph('<para align=center color=white>' + str(compilationData[61]) + '</para>')
    total_total_total = Paragraph('<para align=center color=white>' + str(compilationData[62]) + '</para>')
    total_percent_billable_total = Paragraph(
        '<para align=center color=white>' + str(compilationData[61] / 200 * 100) + ' %</para>')

    total_total_data.append(
        [total_total_text, total_fixed_total_column, total_hourly_total, total_cgy_total, total_nb_total,
         total_pto_total,
         total_billable_total, total_total_total, total_percent_billable_total])

    # ##################################### METRICS CREATION #####################################################
    vp_loss_rev = 0
    smgr_lost_rev = 0
    mgr_lost_rev = 0
    c_lost_rev = 0
    srg_total_lost_revenue = 0

    # ##################################### TABLE CREATION ########################################################    

    tblStyle = TableStyle([('BOX', (0, 0), (-1, -1), 1, colors.black),
                           ('INNERGRID', (0, 0), (-1, -1), 1, colors.black),
                           ('ALIGN', (0, 0), (-1, -1), 'CENTER')])

    total_row_style = TableStyle([('BOX', (0, 0), (-1, -1), 1, colors.black),
                                  ('INNERGRID', (0, 0), (-1, -1), 1, colors.black),
                                  ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#02308C'))])

    vp_table_row = Table(data, repeatRows=1, colWidths=[3.5 * cm, 2 * cm, 2 * cm, 2 * cm, 2 * cm, 2 * cm,
                                                        2 * cm, 2 * cm, 2 * cm])
    vp_table_row.hAlign = 'CENTER'
    vp_table_row.setStyle(tblStyle)
    vp_total_row = Table(vp_total_data, colWidths=[3.5 * cm, 2 * cm, 2 * cm, 2 * cm, 2 * cm, 2 * cm,
                                                   2 * cm, 2 * cm, 2 * cm])
    vp_total_row.hAlign = 'CENTER'
    vp_total_row.setStyle(total_row_style)

    smgr_table_row = Table(smgr_data, colWidths=[3.5 * cm, 2 * cm, 2 * cm, 2 * cm, 2 * cm, 2 * cm,
                                                 2 * cm, 2 * cm, 2 * cm])
    smgr_table_row.hAlign = 'CENTER'
    smgr_table_row.setStyle(tblStyle)

    smgr_total_row = Table(smgr_total_data, colWidths=[3.5 * cm, 2 * cm, 2 * cm, 2 * cm, 2 * cm, 2 * cm,
                                                       2 * cm, 2 * cm, 2 * cm])

    smgr_total_row.hAlign = 'CENTER'
    smgr_total_row.setStyle(total_row_style)

    mgr_table_row = Table(mgr_data, colWidths=[3.5 * cm, 2 * cm, 2 * cm, 2 * cm, 2 * cm, 2 * cm,
                                               2 * cm, 2 * cm, 2 * cm])
    mgr_table_row.hAlign = 'CENTER'
    mgr_table_row.setStyle(tblStyle)

    mgr_total_row = Table(mgr_total_data, colWidths=[3.5 * cm, 2 * cm, 2 * cm, 2 * cm, 2 * cm, 2 * cm,
                                                     2 * cm, 2 * cm, 2 * cm])

    mgr_total_row.hAlign = 'CENTER'
    mgr_total_row.setStyle(total_row_style)

    c_table_row = Table(c_data, colWidths=[3.5 * cm, 2 * cm, 2 * cm, 2 * cm, 2 * cm, 2 * cm,
                                           2 * cm, 2 * cm, 2 * cm])
    c_table_row.hAlign = 'CENTER'
    c_table_row.setStyle(tblStyle)

    c_total_row = Table(c_total_data, colWidths=[3.5 * cm, 2 * cm, 2 * cm, 2 * cm, 2 * cm, 2 * cm,
                                                 2 * cm, 2 * cm, 2 * cm])

    c_total_row.hAlign = 'CENTER'
    c_total_row.setStyle(total_row_style)

    total_total_row = Table(total_total_data, colWidths=[3.5 * cm, 2 * cm, 2 * cm, 2 * cm, 2 * cm, 2 * cm,
                                                         2 * cm, 2 * cm, 2 * cm])

    total_total_row.hAlign = 'CENTER'
    total_total_row.setStyle(total_row_style)

    elements.append(title)
    elements.append(subTitle)
    elements.append(period_text)
    spacer = Spacer(1, 20)
    elements.append(spacer)
    elements.append(vp_table_row)
    elements.append(vp_total_row)
    elements.append(smgr_table_row)
    elements.append(smgr_total_row)
    elements.append(mgr_table_row)
    elements.append(mgr_total_row)
    elements.append(c_table_row)
    elements.append(c_total_row)
    spacer = Spacer(width=1, height=10)
    elements.append(spacer)
    elements.append(total_total_row)

    buffer = BytesIO()
    employeeHoursCompilationReportDoc = SimpleDocTemplate(buffer, pagesize=[A4[0], A4[1]], leftMargin=15,
                                                          rightMargin=15,
                                                          topMargin=15, bottomMargin=5)
    employeeHoursCompilationReportDoc.build(elements)
    pdf_value = buffer.getvalue()
    buffer.close()

    response = HttpResponse(content_type='application/pdf')
    response.write(pdf_value)
    response['Content-Disposition'] = 'attachment; fileName="Employee Compilation Report.pdf"'

    return response


# Archived Functions #
'''
mgr_fixed = compilationData[14]
    mgr_hourly = compilationData[15]
    mgr_cgy = compilationData[16]
    mgr_nb = compilationData[17]
    mgr_pto = compilationData[18]

    mgrEmployeeFixedColumn = 0
    mgrEmployeeHourlyColumn = 0
    mgrEmployeeCGYColumn = 0
    mgrEmployeeNBColumn = 0
    mgrEmployeePTOColumn = 0

    for emp in mgrs:
        employeeColumn = Paragraph('<para align=left>' + str(emp['user__username']) + '</para>', styles['Normal'])
        for item in mgr_fixed:
            if item['employee_id'] == emp['employee_id']:
                mgrEmployeeFixedColumn = str(item['fixed_hours_by_employee_sum'])
        for item in mgr_hourly:
            if item['employee_id'] == emp['employee_id']:
                mgrEmployeeHourlyColumn = Paragraph(
                    '<para align=center>' + str(item['hourly_hours_by_employee_sum']) + '</para>', styles['Normal'])
                # data.append([employeeHourlyColumn])
        for item in mgr_cgy:
            if item['employee_id'] == emp['employee_id']:
                mgrEmployeeCGYColumn = Paragraph('<para align=center>' + str(item['cgy_hours_by_employee_sum']))
        for item in mgr_nb:
            if item['employee_id'] == emp['employee_id']:
                mgrEmployeeNBColumn = Paragraph(
                    '<para align=center>' + str(item['non_billable_hours_sum']) + '</para>', styles['Normal'])
        for item in mgr_pto:
            if item['employee_id'] == emp['employee_id']:
                mgrEmployeePTOColumn = Paragraph(
                    '<para align=center>' + str(item['pto_hours_by_employee_sum']) + '</para>', styles['Normal'])
        employeeBillableColumn = str("0")
        employeeTotalColumn = str("0")
        employeePercentBillableColumn = str("0")

        data.append(
            [employeeColumn, mgrEmployeeFixedColumn, mgrEmployeeHourlyColumn, mgrEmployeeCGYColumn, mgrEmployeeNBColumn,
             mgrEmployeePTOColumn])




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
