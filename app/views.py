import datetime
import json
import os
import time
from datetime import timedelta
from datetime import datetime
from io import BytesIO

import pandas
import numpy as np
import sendgrid
import six
from django.contrib.auth import update_session_auth_hash, logout
from django.contrib.auth.tokens import PasswordResetTokenGenerator, default_token_generator
from django.core import serializers
from django.utils.http import urlsafe_base64_decode
from sendgrid import Content
from sendgrid.helpers.mail import Mail, From, To, Subject, DynamicTemplateData
from dateutil.relativedelta import relativedelta
from django.contrib import auth, messages
from django.core.mail import EmailMessage
from django.core.paginator import Paginator
from django.db.models import F, Count
from django.db.models import Max, Case, When, Q, DecimalField
from django.db.models.functions import Coalesce, ExtractMonth
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django_pandas.io import read_frame
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT 
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from .filters import TimesheetFilter, ExpenseFilter, AdminTodoListFilter, TimesheetFilterPrevious, EngagementFilter
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


def logout_view(request):
    logout(request)

    return redirect('login')


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
        budget_calc=Max('budget_amount') / 300).filter(time_code__lt=900, is_complete=False,
                                                       engagement_id__in=user_assignments).order_by(
        '-engagement_hours_sum', '-fye', 'time_code',
        'provider_id')

    today = date.today()
    if today.weekday() == 6:
        week_beg = today
        week_end = today + timedelta(days=6)
    else:
        week_beg = today - timedelta(days=today.weekday()) - timedelta(days=1)
        week_end = week_beg + timedelta(days=6)

    timesheet_entries = Time.objects.all().filter(employee__user__username=request.user.username).filter(
        ts_date__year=today.year)

    hours_per_month = timesheet_entries.annotate(month=ExtractMonth('ts_date')).values('month').annotate(total=Coalesce(
        Sum('hours'), 0, output_field=DecimalField())).values('month', 'total').order_by('month')

    # Coalesce(Sum('hours'), 0, output_field=DecimalField())

    cw_timesheet_entries = timesheet_entries.filter(employee__user__username=request.user.username).filter(
        ts_date__gte=week_beg).filter(ts_date__lte=week_end)

    billable_hours_sum = cw_timesheet_entries.exclude(engagement__type_id='N').aggregate(
        amount=Coalesce(Sum('hours'), 0, output_field=DecimalField(0.00)))

    non_billable_hours_sum = cw_timesheet_entries.filter(engagement__type_id='N').aggregate(
        amount=Coalesce(Sum('hours'), 0, output_field=DecimalField(0.00)))

    ytd_billable_hours_sum = timesheet_entries.exclude(engagement__type_id='N').aggregate(
        amount=Coalesce(Sum('hours'), 0, output_field=DecimalField(0.00)))

    ytd_none_billable_hours_sum = timesheet_entries.filter(engagement__type_id='N').aggregate(
        amount=Coalesce(Sum('hours'), 0, output_field=DecimalField(0.00)))

    total_hours_sum = billable_hours_sum['amount'] + non_billable_hours_sum['amount']

    ytd_start = date(today.year, 1, 1)
    number_of_workdays = np.busday_count(ytd_start, today)
    billable_weeks = number_of_workdays / 5
    monthly_billable_hours = number_of_workdays * 8

    billable_percentage = round((ytd_billable_hours_sum['amount'] / monthly_billable_hours) * 100, 2)

    employee_td_entries = Todolist.objects.values('todo_date',
                                                  'engagement__parent_id',
                                                  'engagement__parent_id__parent_name',
                                                  'engagement__provider_id',
                                                  'engagement__provider_id__provider_name',
                                                  'engagement__fye',
                                                  'engagement__time_code',
                                                  'engagement__time_code__time_code_desc').filter(
        employee__user__username=request.user.username).filter(todo_date=today).order_by('todo_date').annotate(
        hsum=Sum('anticipated_hours'))

    context = {'page_title': 'Dashboard', 'user_engagements': user_engagements, 'today': today, 'week_beg': week_beg,
               'week_end': week_end, 'user_info': user_info, 'cw_timesheet_entries': cw_timesheet_entries,
               'employee_td_entries': employee_td_entries, 'user_assignments': user_assignments,
               'billable_hours_sum': billable_hours_sum, 'total_hours_sum': total_hours_sum,
               'billable_percentage': billable_percentage,
               'hours_per_month': hours_per_month, 'monthly_billable_hours': monthly_billable_hours,
               'ytd_billable_hours_sum': ytd_billable_hours_sum, 'non_billable_hours_sum': non_billable_hours_sum,
               'ytd_none_billable_hours_sum': ytd_none_billable_hours_sum, 'ts_is_submitted': ts_is_submitted}
    return render(request, 'dashboard.html', context)


def getCompilationData(mnth):
    number_of_workdays = 0
    billable_weeks = 0
    useless_var = number_of_workdays + billable_weeks
    useless_var_two = number_of_workdays + billable_weeks
    if mnth == 'YTD':
        current_year = datetime.now().year
        ytd_hours_by_employee = Time.objects.filter(employee__is_billable=True, ts_date__year=current_year).values(
            'employee_id', 'employee__title', 'employee__user__username')

        fixed_hours_by_employee = ytd_hours_by_employee.filter(engagement__type_id='F').annotate(
            fixed_hours_by_employee_sum=Sum('hours'))

        hourly_hours_by_employee = ytd_hours_by_employee.filter(engagement__type_id='H').annotate(
            hourly_hours_by_employee_sum=Sum('hours'))

        cgy_hours_by_employee = ytd_hours_by_employee.filter(engagement__type_id='C').annotate(
            cgy_hours_by_employee_sum=Sum('hours'))

        non_billable_hours_by_employee = ytd_hours_by_employee.filter(engagement__type_id='N').exclude(
            engagement__time_code__gte=980).values('employee_id').annotate(non_billable_hours_sum=Sum('hours'))

        pto_hours_by_employee = ytd_hours_by_employee.filter(engagement__time_code__gte=980).annotate(
            pto_hours_by_employee_sum=Sum('hours'))

        billable_hours_by_employee = ytd_hours_by_employee.exclude(engagement__type_id='N').annotate(
            billable_hours_sum=Sum('hours'))

        total_hours_by_employee = ytd_hours_by_employee.annotate(total_hours_sum=Sum('hours'))

        today = date.today()
        ytd_start = date(today.year, 1, 1)
        number_of_workdays = np.busday_count(ytd_start, today)
        billable_weeks = number_of_workdays / 5
        monthly_billable_hours = billable_weeks * 40

    else:
        current_year = datetime.now().year

        month_hours_by_employee = Time.objects.filter(employee__is_billable=True, ts_date__month=mnth,
                                                      ts_date__year=current_year).values(
            'employee_id', 'employee__title', 'employee__user__username')

        fixed_hours_by_employee = month_hours_by_employee.filter(engagement__type_id='F').annotate(
            fixed_hours_by_employee_sum=Sum('hours')).order_by('employee__user__last_name')

        hourly_hours_by_employee = month_hours_by_employee.filter(engagement__type_id='H').annotate(
            hourly_hours_by_employee_sum=Sum('hours')).order_by('employee__user__last_name')

        cgy_hours_by_employee = month_hours_by_employee.filter(engagement__type_id='C').annotate(
            cgy_hours_by_employee_sum=Sum('hours'))

        non_billable_hours_by_employee = month_hours_by_employee.filter(engagement__type_id='N', ).exclude(
            engagement__time_code__gte=980).annotate(non_billable_hours_sum=Sum('hours'))

        pto_hours_by_employee = month_hours_by_employee.filter(engagement__time_code__gte=980).annotate(
            pto_hours_by_employee_sum=Sum('hours'))

        billable_hours_by_employee = month_hours_by_employee.exclude(engagement__type_id='N').annotate(
            billable_hours_sum=Sum('hours'))

        total_hours_by_employee = month_hours_by_employee.annotate(total_hours_sum=Sum('hours'))

        next_month = int(mnth) + 1
        next_year = current_year + 1
        if int(mnth) < 9:
            number_of_workdays = np.busday_count(str(current_year) + '-0' + str(mnth),
                                                 str(current_year) + '-0' + str(next_month))
        elif int(mnth) == 9:
            number_of_workdays = np.busday_count(str(current_year) + '-0' + str(mnth),
                                                 str(current_year) + '-' + str(next_month))
        elif int(mnth) == 12:
            number_of_workdays = np.busday_count(str(current_year) + '-' + str(mnth),
                                                 str(next_year) + '-01')
        else:
            number_of_workdays = np.busday_count(str(current_year) + '-' + str(mnth),
                                                 str(current_year) + '-' + str(next_month))

        billable_weeks = number_of_workdays / 5
        monthly_billable_hours = billable_weeks * 40

    # VP HOURS ##########
    vp_fixed_hours_by_employee = fixed_hours_by_employee.filter(Q(employee__title='EVP') | Q(employee__title='VP'))
    vp_hourly_hours_by_employee = hourly_hours_by_employee.filter(employee__title='VP')
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
    srg_total_fixed_hours = vp_total_fixed_hours['amount'] + smgr_total_fixed_hours['amount'] + mgr_total_fixed_hours['amount'] + c_total_fixed_hours['amount']
    srg_total_hourly_hours = vp_total_hourly_hours['amount'] + smgr_total_hourly_hours['amount'] + mgr_total_hourly_hours['amount'] + c_total_hourly_hours['amount']
    srg_total_cgy_hours = vp_total_cgy_hours['amount'] + smgr_total_cgy_hours ['amount'] + mgr_total_cgy_hours['amount'] + c_total_cgy_hours['amount']
    srg_total_non_billable_hours = vp_total_non_billable_hours['amount'] + smgr_total_non_billable_hours['amount'] + mgr_total_non_billable_hours['amount'] + c_total_non_billable_hours['amount']
    srg_total_pto_hours = vp_total_pto_hours['amount'] + smgr_total_pto_hours['amount'] + mgr_total_pto_hours['amount'] + c_total_pto_hours['amount']
    srg_total_billable_hours = vp_total_billable_hours['amount'] + smgr_total_billable_hours['amount'] + mgr_total_billable_hours['amount'] + c_total_billable_hours['amount']
    srg_total_hours = vp_total_hours['amount'] + smgr_total_hours['amount'] + mgr_total_hours['amount'] + c_total_hours['amount']

    vp_rate = get_object_or_404(EmployeeTitles, pk='VP')
    smgr_rate = get_object_or_404(EmployeeTitles, pk='SM')
    mgr_rate = get_object_or_404(EmployeeTitles, pk='M')
    c_rate = get_object_or_404(EmployeeTitles, pk='C')


    vp_loss_rev = vp_total_non_billable_hours['amount'] * vp_rate.rate
    smgr_lost_rev = smgr_total_non_billable_hours['amount'] * smgr_rate.rate
    mgr_lost_rev = mgr_total_non_billable_hours['amount'] * mgr_rate.rate
    c_lost_rev = c_total_non_billable_hours['amount'] * c_rate.rate

    srg_total_lost_revenue = vp_loss_rev + smgr_lost_rev + mgr_lost_rev + c_lost_rev

    number_of_employees = Employee.objects.filter(is_billable=True).aggregate(Count('employee_id'))
    srg_billable_percentage = round((float(srg_total_billable_hours) / (billable_weeks * 40 * number_of_employees['employee_id__count'])) * 100, 0)

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
        vp_loss_rev, smgr_lost_rev, mgr_lost_rev, c_lost_rev, srg_total_lost_revenue, number_of_workdays, billable_weeks, \
        srg_billable_percentage, monthly_billable_hours


def AdminDashboard(request):
    user_info = get_object_or_404(User, pk=request.user.id)
    employee_info = get_object_or_404(Employee, user=user_info.id)
    today = date.today()
    # today_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    week_beg = today - timedelta(days=today.weekday())
    week_end = week_beg + timedelta(days=5)
    employees = Employee.objects.values('employee_id', 'user', 'title', 'user__first_name',
                                        'user__last_name').filter(is_billable=True).order_by('title', 'user__last_name')
    vps = employees.filter(title='VP')
    smgrs = employees.filter(title='SM')
    mgrs = employees.filter(title='M')
    consultants = employees.filter(Q(title='C') | Q(title='SC'))
    number_of_employees = len(vps) + len(smgrs) + len(mgrs) + len(consultants)
    current_month = today.month

    if request.method == 'POST':
        month_form = MonthSelectForm(request.POST)
        if month_form.is_valid():
            selected_month = month_form.cleaned_data['month']
            new_data = getCompilationData(selected_month)
            monthly_total_hours = new_data[68] * 8
            total_monthly_billable_hours = new_data[69] * 40 * number_of_employees
            if selected_month == 'YTD':
                pass
            else:
                selected_month = date(today.year, int(selected_month), 1)
            context = {'employee_info': employee_info, 'user_info': user_info, 'today': today, 'week_beg': week_beg,
                       'week_end': week_end, 'employees': employees, 'vps': vps, 'page_title': 'Admin Dashboard',
                       'smgrs': smgrs, 'mgrs': mgrs, 'consultants': consultants,
                       'number_of_employees': number_of_employees,
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
                       'number_of_workdays': new_data[68],
                       'billable_weeks': new_data[69],
                       'srg_billable_percentage': new_data[70],
                       'monthly_billable_hours': new_data[71],
                       'monthly_total_hours': monthly_total_hours,
                       'total_monthly_billable_hours': total_monthly_billable_hours,
                       'selected_month': selected_month,
                       'month_form': month_form}

            return render(request, 'adminDashboard.html', context)

    else:
        month_form = MonthSelectForm(initial={'month': current_month})
        current_month_data = getCompilationData(current_month)
        monthly_total_hours = current_month_data[68] * 8
        total_monthly_billable_hours = current_month_data[69] * 40 * number_of_employees
        context = {'employee_info': employee_info, 'user_info': user_info, 'today': today, 'week_beg': week_beg,
                   'week_end': week_end, 'employees': employees, 'vps': vps, 'page_title': 'Admin Dashboard',
                   'smgrs': smgrs, 'mgrs': mgrs, 'consultants': consultants, 'number_of_employees': number_of_employees,
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
                   'number_of_workdays': current_month_data[68],
                   'billable_weeks': current_month_data[69],
                   'srg_billable_percentage': current_month_data[70],
                   'monthly_billable_hours': current_month_data[71],
                   'monthly_total_hours': monthly_total_hours,
                   'total_monthly_billable_hours': total_monthly_billable_hours,
                   'selected_month': today,
                   'month_form': month_form}

        return render(request, 'adminDashboard.html', context)


def EngagementDashboard(request):
    user_info = get_object_or_404(User, pk=request.user.id)
    today = date.today()
    week_beg = today - timedelta(days=today.weekday()) - timedelta(days=1)
    week_end = week_beg + timedelta(days=6)
    parents = list(Parent.objects.all())
    parents = sorted(parents, key=lambda x: (x.parent_id.isdigit(), x.parent_id))

    # engagements = Engagement.objects.annotate(total_hours=Sum('time__hours'))

    engagements = Engagement.objects.values("engagement_id", "engagement_srg_id", "parent_id", "parent__parent_name",
                                            "provider_id", "provider__provider_name", "time_code",
                                            "time_code__time_code_desc",
                                            "is_complete", "fye", "budget_hours", "budget_amount").annotate(
        engagement_hours_sum=Sum('time__hours'), budget_calc=Max('budget_amount') / 300).order_by('-fye', 'time_code',
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

            if 'createEngagementAssign' in request.POST:
                engagement_id = get_object_or_404(Engagement, engagement_srg_id=engagement_srg_id)
                return redirect('admin-assign', engagement_id.engagement_id)
            else:
                return redirect('engagement-dashboard')
    else:
        createEngagementForm = CreateEngagementForm()

    context = {'user_info': user_info, 'parents': parents, 'createEngagementForm': createEngagementForm,
               'engagements': engagements, 'today': today, 'week_beg': week_beg, 'week_end': week_end,
               'page_title': 'Engagements'}

    return render(request, 'engagementDashboard.html', context)


def AdminAssignments(request):
    user_info = get_object_or_404(User, pk=request.user.id)

    period_beg = date.today()
    today = date.today()
    week_beg = today - timedelta(days=today.weekday()) - timedelta(days=1)
    week_end = week_beg + timedelta(days=6)
    queryset = Engagement.objects.none()
    if request.GET:
        queryset = Engagement.objects.values('engagement_id', 'engagement_srg_id',
                                             'parent__parent_name', 'provider',
                                             'provider__provider_name', 'time_code',
                                             'time_code__time_code_desc',
                                             'fye').annotate(
            assignment_count=Count('assignments__engagement_id')).order_by('parent__parent_name', 'provider', 'fye')

    f = EngagementFilter(request.GET, queryset=queryset)
    employee_list = Employee.objects.order_by('user')

    form = EmployeeFilterForm

    context = {'user_info': user_info, 'week_beg': week_beg, 'week_end': week_end, 'today': today, 'filter': f,
               'employee_list': employee_list, 'form': form, 'page_title': 'Assignments'}

    return render(request, 'adminAssignments.html', context)


def AdminEngagementDetail(request, pk):
    user_info = get_object_or_404(User, pk=request.user.id)

    period_beg = date.today()
    today = date.today()
    week_beg = today - timedelta(days=today.weekday()) - timedelta(days=1)
    week_end = week_beg + timedelta(days=6)

    engagement_instance = get_object_or_404(Engagement, pk=pk)
    engagement_notes = EngagementNotes.objects.filter(engagement=engagement_instance.engagement_id).order_by(
        '-note_date')

    budget_calc = engagement_instance.budget_amount // 300

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

    employee_engagement_hours = Employee.objects.select_related().all()

    engagement_td_hours_by_employee = Todolist.objects.filter(engagement=engagement_instance.engagement_id).values(
        'engagement', 'employee__user__username').annotate(td_hours=Sum('anticipated_hours'))

    engagement_ts_hours_by_employee = Time.objects.filter(engagement=engagement_instance.engagement_id).values(
        'engagement', 'employee__user__username').annotate(ts_hours=Sum('hours'))

    if len(engagement_ts_hours_by_employee) >= len(engagement_td_hours_by_employee):
        ts_vs_todo_data = engagement_ts_hours_by_employee
        for emp in engagement_ts_hours_by_employee:
            if engagement_td_hours_by_employee.filter(
                    employee__user__username=emp['employee__user__username']).exists():
                emp_data = engagement_td_hours_by_employee.filter(
                    employee__user__username=emp['employee__user__username']).values('td_hours')
                for i in emp_data:
                    emp['td_hours'] = i['td_hours']
            else:
                emp['td_hours'] = 0
            emp['variance'] = emp['ts_hours'] - emp['td_hours']
        ts_vs_todo_data = engagement_ts_hours_by_employee
    else:
        for emp in engagement_td_hours_by_employee:
            if engagement_ts_hours_by_employee.filter(
                    employee__user__username=emp['employee__user__username']).exists():
                emp_data = engagement_ts_hours_by_employee.filter(
                    employee__user__username=emp['employee__user__username']).values('ts_hours')
                for i in emp_data:
                    emp['ts_hours'] = i['ts_hours']
            else:
                emp['ts_hours'] = 0
            emp['variance'] = emp['ts_hours'] - emp['td_hours']
        ts_vs_todo_data = engagement_td_hours_by_employee

    note_form = CreateEngagementNote()
    if request.method == 'POST':
        note_form = CreateEngagementNote(request.POST)
        if note_form.is_valid():
            employee_instance = get_object_or_404(Employee, user=request.user.id)

            new_note = note_form.save(commit=False)
            new_note.employee_id = employee_instance.employee_id
            new_note.engagement = engagement_instance
            new_note.note_date = date.today()
            new_note.save()
            print(engagement_instance.engagement_id)

            return redirect('engagement-detail', engagement_instance.engagement_id)
        else:
            note_form = CreateEngagementNote()

    context = {'user_info': user_info, 'today': today, 'week_beg': week_beg, 'week_end': week_end,
               'engagement_instance': engagement_instance, 'page_title': 'Engagement Detail',
               'ts_vs_todo_data': ts_vs_todo_data, 'engagement_notes': engagement_notes,
               'engagement_td_hours_by_employee': engagement_td_hours_by_employee,
               'engagement_ts_hours_by_employee': engagement_ts_hours_by_employee,
               'employee_engagement_hours': employee_engagement_hours, 'note_form': note_form,
               'billable_hours_employee': billable_hours_employee, 'total_billable_hours': total_billable_hours,
               'non_billable_hours_employee': non_billable_hours_employee, 'budget_calc': budget_calc,
               'total_non_billable_hours': total_non_billable_hours}

    return render(request, 'adminEngagementDetail.html', context)


def AdminTimesheet(request):
    user_info = get_object_or_404(User, pk=request.user.id)
    today = date.today()
    week_beg = today - timedelta(days=today.weekday())
    week_end = week_beg + timedelta(days=5)
    queryset = Time.objects.none()
    q_total = 0
    if request.GET:
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
                                       'employee__title__rate',
                                       'hours',
                                       'note').order_by('ts_date', 'engagement__parent__parent_name',
                                                        'engagement__provider',
                                                        'engagement__fye')

    f = TimesheetFilter(request.GET, queryset=queryset)
    q_total = f.qs.aggregate(total_hours=Sum('hours')).get('total_hours', 0)
    q_employees = f.qs.values('employee__user__username', 'employee__title__rate').order_by('employee').annotate(
        hours_sum=Sum('hours')).order_by('-hours_sum').annotate(dollars_sum=F('hours_sum') * F('employee__title__rate'))
    q_grand_total = q_employees.aggregate(grand_total=Sum('hours')).get('grand_total', 0)
    q_dollars_total = q_employees.aggregate(dollars_total=Sum('dollars_sum')).get('dollars_total', 0)

    q_engagements = f.qs.values('engagement__engagement_id', 'engagement__engagement_srg_id',
                                'engagement__parent__parent_name', 'engagement__provider',
                                'engagement__provider__provider_name', 'engagement__time_code',
                                'engagement__time_code__time_code_desc', 'engagement__fye').order_by(
        'engagement__engagement_srg_id').annotate(hours_sum=Sum('hours')).order_by('-hours_sum')[:3]

    f_start_date = f.form['start_date']
    f_end_date = f.form['end_date']
    f_employee = f.form['employee'].value()

    if request.method == 'GET' and 'extract_button' in request.GET:
        if f_employee == '':
            matching_expenses = Expense.objects.values('date','employee__user__username', 'engagement__engagement_id',
                                                       'engagement__engagement_srg_id',
                                                       'engagement__parent__parent_name', 'engagement__provider',
                                                       'engagement__provider__provider_name', 'engagement__time_code',
                                                       'engagement__time_code__time_code_desc', 'engagement__fye',
                                                       'expense_category',
                                                       'expense_amount', 'expense_note').filter(
                date__gte=datetime.strptime(f_start_date.value(), "%Y-%m-%d"),
                date__lte=datetime.strptime(f_end_date.value(), "%Y-%m-%d")).order_by('-date')
        else:
            matching_expenses = Expense.objects.values('date','employee__user__username', 'engagement__engagement_id',
                                                       'engagement__engagement_srg_id',
                                                       'engagement__parent__parent_name', 'engagement__provider',
                                                       'engagement__provider__provider_name', 'engagement__time_code',
                                                       'engagement__time_code__time_code_desc', 'engagement__fye',
                                                       'expense_category',
                                                       'expense_amount', 'expense_note').filter(
                date__gte=datetime.strptime(f_start_date.value(), "%Y-%m-%d"),
                date__lte=datetime.strptime(f_end_date.value(), "%Y-%m-%d"),
                employee=f_employee).order_by('-date')

        ts_data = read_frame(f.qs)
        ts_data['hours'] = pandas.to_numeric(ts_data['hours'], errors='coerce')
        ts_data = ts_data.rename(columns={'ts_date': 'Date', 'employee__user__username': 'Employee',
                                          'engagement__engagement_srg_id': 'SRG_ID',
                                          'engagement__parent__parent_name': 'Parent',
                                          'engagement__provider': 'Provider #',
                                          'engagement__provider__provider_name': 'Provider Name',
                                          'engagement__time_code': 'Time Code',
                                          'engagement__time_code__time_code_desc': 'Time Code Description',
                                          'engagement__fye': 'FYE', 'engagement__type_id': 'Bill Type',
                                          'engagement__is_rac': 'RAC Y/N',
                                          'engagement__engagement_hourly_rate': 'Engagement Rate',
                                          'employee__title__rate': 'Employee Rate',
                                          'hours': 'Hours', 'note': 'Note'})

        ex_data = read_frame(matching_expenses)
        ex_data['expense_amount'] = pandas.to_numeric(ex_data['expense_amount'], errors='coerce')
        fname = 'EmployeeTimesheetCompilation'

        response = HttpResponse(content_type='application/vns.ms-excel')
        response['Content-Disposition'] = 'attachment; filename=' + fname + '.xlsx'
        with pandas.ExcelWriter(response, engine='xlsxwriter') as writer:
            ts_data.to_excel(writer, sheet_name='SRG Timesheet Compilation', index=False, header=True)
            ex_data.to_excel(writer, sheet_name='SRG Expense Compilation', index=False, header=True)
            # df_hfy.to_excel(writer, sheet_name=('PFY ' + fye), index=False, header=True)

            return response

    context = {'filter': f, 'page_title': 'Extract Billing Data', 'today': today, 'week_beg': week_beg,
               'week_end': week_end, 'user_info': user_info, 'q_total': q_total, 'q_employees': q_employees,
               'q_engagements': q_engagements, 'q_dollars_total': q_dollars_total, 'q_grand_total': q_grand_total}

    return render(request, 'adminTimesheet.html', context)


def getStaffWeekHours(emp, per_beg, per_end):
    data = list(Todolist.objects.filter(employee_id=emp, todo_date__gte=per_beg).filter(
        todo_date__lte=per_end).annotate(
        total_hours_sum=Coalesce(Sum('anticipated_hours'), 0, output_field=DecimalField()),
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
    ))
    return data


def getStaffNotInTodoList(per_beg, per_end):
    data = Todolist.objects.values('employee__user__username').filter(todo_date__gte=per_beg).filter(
        todo_date__lte=per_end)

    data_none = Employee.objects.exclude(user__username__in=data)

    return data_none

def getSaturdaysBetweenDates(per_beg, per_end):
    """
    Generate a lit of all Saturdays between per_beg and per_end
    """
    saturdays = []
    current_date = per_beg

    # find the first Saturday after or ont he per_beg
    while current_date.weekday() != 5:
        current_date += timedelta(days=1)

    # Add all Saturdays until the end_date
    while current_date <= per_end:
        saturdays.append(current_date)
        current_date += timedelta(days=7)

    return saturdays

def custom_json_encoder(obj):
    if isinstance(obj, date):
        return obj.strftime('%Y-%m-%d')  # Convert date to a string in 'YYYY-MM-DD' format
    raise TypeError(f"Type {type(obj)} not serializable")

def getTimesheetSubmissionLog(request, per_end):

    data = Time.objects.values('employee__user__username','submitted_on', 'ts_period').annotate(
        hours_sum=Sum('hours')).filter(ts_period=per_end).order_by('ts_period')

    print(data)
    return JsonResponse({'data': list(data)}, safe=False)


def AdminTimesheetReview(request):
    user_info = get_object_or_404(User, pk=request.user.id)
    employee_info = get_object_or_404(Employee, user=user_info.id)
    today = date.today()
    week_beg = today - timedelta(days=today.weekday())
    week_end = week_beg + timedelta(days=5)
    employees = Employee.objects.filter(is_billable=True).order_by('user').select_related('user')

    # Define the range for the periods
    today = date.today() + timedelta(days=14)
    start_of_year = today.replace(month=1, day=1)

    # Generate List of Periods
    periods = getSaturdaysBetweenDates(start_of_year, today)

    # Fetch data from Time model
    employee_ts_submission_data = Time.objects.filter(ts_period__in=periods).select_related('employee')

    # Organize data as a dictionary for efficient lookup
    time_lookup = {}

    preprocessed_data = {}


    context = {'user_info': user_info, 'employee_info': employee_info, 'today': today, 'week_beg': week_beg,
               'week_end': week_end, 'employees': employees, 'periods': periods, 'time_lookup': time_lookup,
               'page_title': 'Timesheet Review', 'preprocessed_data': json.dumps(preprocessed_data, default=custom_json_encoder)}

    return render(request, 'adminTimesheetReview.html', context)

def getStaffToDoList(request, emp_id):
    emp = get_object_or_404(Employee, pk=emp_id)
    today = date.today()
    week_beg = today - timedelta(days=today.weekday()) - timedelta(days=1)
    week_end = week_beg + timedelta(days=6)
    emp_td = Todolist.objects.values('todolist_id', 'todo_date', 'todo_date_end', 'engagement__provider',
                                     'engagement__provider__provider_name',
                                     'engagement__time_code', 'engagement__time_code__time_code_desc',
                                     'engagement__fye', 'anticipated_hours',
                                     'engagement__engagement_srg_id').filter(
        todo_date__year=today.year,
        employee=emp_id).order_by('todo_date')

    emp_td_list = list(emp_td)

    total_billable_hours = emp_td.exclude(engagement__type_id='N').filter(todo_date__gte=week_beg,
                                                                          todo_date__lte=week_end).aggregate(
        total_billable_hours_sum=Coalesce(Sum('anticipated_hours'), 0, output_field=DecimalField()))
    total_non_billable_hours = emp_td.filter(engagement__type_id='N', todo_date__gte=week_beg,
                                             todo_date__lte=week_end).aggregate(
        total_non_billable_hours_sum=Coalesce(Sum('anticipated_hours'), 0, output_field=DecimalField()))
    total_hours = emp_td.filter(todo_date__gte=week_beg, todo_date__lte=week_end).aggregate(
        total_hours_sum=Coalesce(Sum('anticipated_hours'), 0, output_field=DecimalField()))
    hours_avail = 40 - total_hours['total_hours_sum']

    next_week_beg = week_beg + timedelta(days=7)
    next_week_end = week_end + timedelta(days=7)

    next_billable_hours = emp_td.exclude(engagement__type_id='N').filter(todo_date__gte=next_week_beg,
                                                                         todo_date__lte=next_week_end).aggregate(
        next_billable_hours_sum=Coalesce(Sum('anticipated_hours'), 0, output_field=DecimalField()))
    next_non_billable_hours = emp_td.filter(engagement__type_id='N', todo_date__gte=next_week_beg,
                                            todo_date__lte=next_week_end).aggregate(
        next_non_billable_hours_sum=Coalesce(Sum('anticipated_hours'), 0, output_field=DecimalField()))
    next_hours = emp_td.filter(todo_date__gte=next_week_beg, todo_date__lte=next_week_end).aggregate(
        next_hours_sum=Coalesce(Sum('anticipated_hours'), 0, output_field=DecimalField()))
    next_avail = 40 - next_hours['next_hours_sum']

    return JsonResponse({'emp_td_list': emp_td_list, 'today': today, 'week_beg': week_beg, 'week_end': week_end,
                         'next_week_beg': next_week_beg, 'next_week_end': next_week_end,
                         'next_billable_hours': next_billable_hours, 'next_non_billable_hours': next_non_billable_hours,
                         'next_hours': next_hours, 'next_avail': next_avail,
                         'total_hours': total_hours, 'total_billable_hours': total_billable_hours,
                         'total_non_billable_hours': total_non_billable_hours, 'hours_avail': hours_avail}, safe=False)


def AdminPlanning(request):
    user_info = get_object_or_404(User, pk=request.user.id)
    period_beg = date.today()
    today = date.today()
    week_beg = today - timedelta(days=today.weekday()) - timedelta(days=1)
    week_end = week_beg + timedelta(days=6)
    period_days = []
    for i in range(180):
        period_days.append(period_beg + timedelta(days=i))

    employees = Employee.objects.values('user__username', 'employee_id', 'user__last_name').filter(
        is_billable=True).order_by('user__last_name')
    # todolists = Todolist.objects.values('employee__user__username', 'engagement__provider',
    #                                    'engagement__provider__provider_name', 'todo_date',
    #                                    'engagement__engagement_srg_id', 'anticipated_hours').order_by('todo_date',
    #                                                                                                   'employee__user__username')
    '''
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
    
    '''

    # todo_filter = AdminTodoListFilter(request.GET, queryset=todolists)

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

    context = {'employees': employees, 'period_days': period_days,
               'week_beg': week_beg, 'week_end': week_end,
               'page_title': 'Admin Planning', 'today': today, 'user_info': user_info
               }
    return render(request, 'adminPlanningUpdate.html', context)


def AdminEmployeeDashboard(request, pk, per_beg, per_end):
    user_info = get_object_or_404(User, employee__employee_id=pk)
    user_filter_list = pk.split(".")
    first_name = user_info.first_name
    last_name = user_info.last_name
    today = date.today()
    per_beg_object = datetime.strptime(per_beg, "%Y-%m-%d")
    per_end_object = datetime.strptime(per_end, "%Y-%m-%d")

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

    timesheet_hours = Time.objects.all().filter(employee_id=user_info.employee.employee_id).filter(
        ts_date__gte=per_beg).filter(ts_date__lte=per_end).aggregate(
        amount=Coalesce(Sum('hours'), 0, output_field=DecimalField(0.00)))

    todolist_entries = Todolist.objects.filter(employee_id=user_info.employee.employee_id).filter(
        todo_date__gte=per_beg).filter(todo_date__lte=per_end)

    todolist_hours = todolist_entries.aggregate(
        amount=Coalesce(Sum('anticipated_hours'), 0, output_field=DecimalField(0.00)))

    todolist_hours_by_engagement = todolist_entries.values('engagement_id', 'engagement', 'engagement__time_code',
                                                           'engagement__time_code__time_code_desc', 'engagement__fye',
                                                           'engagement__parent_id', 'engagement__parent__parent_name',
                                                           'engagement__provider',
                                                           'engagement__provider__provider_name').annotate(
        amount=Sum('anticipated_hours')).order_by('-amount')

    todolist_hours_by_days = todolist_entries.values('todo_date').annotate(
        anticipated_hours_sum=Coalesce(Sum('anticipated_hours'), 0, output_field=DecimalField(0.00)))

    week_labels = []
    i = per_beg_object
    while i <= per_end_object:
        week_labels.append(i)
        i += timedelta(days=1)

    # billable_hours_sum = timesheet_entries.exclude(Q(engagement__type_id='N') | Q(time_type_id_id='N')).aggregate(
    #    amount=Coalesce(Sum('hours'), 0, output_field=DecimalField(0.00)))

    # non_billable_hours_sum = timesheet_entries.filter(Q(engagement__type_id='N') | Q(time_type_id_id='N')).aggregate(
    #    amount=Coalesce(Sum('hours'), 0, output_field=DecimalField(0.00)))

    employee_td_entries_all = Todolist.objects.values('todo_date',
                                                      'engagement__engagement_srg_id',
                                                      'engagement__parent_id',
                                                      'engagement__parent_id__parent_name',
                                                      'engagement__provider_id',
                                                      'engagement__provider_id__provider_name',
                                                      'engagement__time_code',
                                                      'engagement__time_code__time_code_desc').filter(
        employee_id=user_info.employee.employee_id).order_by('todo_date').annotate(
        hsum=Sum('anticipated_hours'))

    employee_td_entries = employee_td_entries_all.filter(todo_date=today).order_by('todo_date')

    context = {'per_end_object': per_end_object, 'per_beg_object': per_beg_object, 'user_info': user_info,
               'timesheet_hours': timesheet_hours, 'today': today, 'first_name': first_name, 'last_name': last_name,
               'user_engagements': user_engagements, 'week_beg': per_beg_object, 'week_end': per_end_object,
               'week_labels': week_labels,
               'page_title': 'Employee Detail', 'todolist_hours': todolist_hours,
               'todolist_hours_by_days': todolist_hours_by_days,
               'employee_td_entries': employee_td_entries, 'employee_td_entries_all': employee_td_entries_all,
               'todolist_hours_by_engagement': todolist_hours_by_engagement}
    return render(request, 'adminEmployeeDashboard.html', context)


def EmployeeTimesheetPrevious(request):
    user_info = get_object_or_404(User, pk=request.user.id)
    ts_is_submitted = user_info.employee.ts_is_submitted
    today = date.today()
    week_beg = today - timedelta(days=today.weekday())
    week_end = week_beg + timedelta(days=5)
    queryset = Time.objects.none()
    if request.GET:
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
                                                        'engagement__fye').filter(employee_id=user_info.employee)

    f = TimesheetFilterPrevious(request.GET, queryset=queryset)
    qs = f.qs

    qs_hours_total_f = qs.aggregate(qs_hours_sum=Sum('hours'))

    f_start_date = f.form['start_date']
    f_end_date = f.form['end_date']

    if request.method == 'GET' and 'extract_button' in request.GET:
        matching_expenses = Expense.objects.filter(employee_id=user_info.employee,
                                                   date__gte=datetime.strptime(f_start_date.value(), "%Y-%m-%d"),
                                                   date__lte=datetime.strptime(f_end_date.value(), "%Y-%m-%d"))
        ts_data = read_frame(f.qs)

        ex_data = read_frame(matching_expenses)

        fname = 'EmployeeTimesheetCompilation'

        response = HttpResponse(content_type='application/vns.ms-excel')
        response['Content-Disposition'] = 'attachment; filename=' + fname + '.xlsx'
        with pandas.ExcelWriter(response, engine='xlsxwriter') as writer:
            ts_data.to_excel(writer, sheet_name='SRG Timesheet Compilation', index=False, header=True)
            ex_data.to_excel(writer, sheet_name='SRG Expense Compilation', index=False, header=True)
            # df_hfy.to_excel(writer, sheet_name=('PFY ' + fye), index=False, header=True)

            return response

    context = {'filter': f, 'page_title': 'Extract Timesheeet', 'today': today, 'week_beg': week_beg,
               'week_end': week_end, 'user_info': user_info, 'qs_hours_total_f': qs_hours_total_f,
               'ts_is_submitted': ts_is_submitted}

    return render(request, 'employeeTimesheetPrevious.html', context)


def EmployeeTimesheetReview(request):
    user_info = get_object_or_404(User, pk=request.user.id)
    ts_is_submitted = user_info.employee.ts_is_submitted
    today = date.today()
    print(today.weekday())
    if today.weekday() == 4:
        last_week_beg = today - timedelta(days=5)
        last_week_end = last_week_beg + timedelta(days=6)
    elif today.weekday() == 5:
        last_week_beg = today - timedelta(days=6)
        last_week_end = today
    elif today.weekday() == 6:
        last_week_end = today - timedelta(days=1)
        last_week_beg = last_week_end - timedelta(days=6)
    else:
        last_week_beg = today - timedelta(days=7) - timedelta(days=date.today().weekday()) - timedelta(days=1)
        last_week_end = last_week_beg + timedelta(days=6)

    current_week = []
    current_week_ts = {}

    for i in range(7):
        current_week.append(last_week_beg + timedelta(days=i))

    employee_ts_entries = Time.objects.filter(employee__user__username=request.user.username).filter(
        ts_date__gte=last_week_beg).filter(ts_date__lte=last_week_end).order_by('ts_date')

    user_engagements = Engagement.objects.select_related().filter(
        is_complete=False, assignments__employee__employee_id=user_info.employee.employee_id).order_by('provider_id')

    employee_hours_by_day = employee_ts_entries.values('ts_date').annotate(ts_hours=Sum('hours'))

    total_weekly_hours = employee_ts_entries.aggregate(hours_sum=Coalesce(Sum('hours'), 0, output_field=DecimalField()))

    employee_weekly_expenses = Expense.objects.values('expense_id', 'engagement__provider',
                                                      'engagement__provider__provider_name',
                                                      'engagement__time_code',
                                                      'engagement__time_code__time_code_desc',
                                                      'expense_category__expense_category',
                                                      'expense_amount',
                                                      'time_type_id').filter(employee=request.user.employee).filter(
        date__gte=last_week_beg).filter(date__lte=last_week_end).order_by('date')

    total_weekly_expenses = employee_weekly_expenses.aggregate(
        expense_sum=Coalesce(Sum('expense_amount'), 0, output_field=DecimalField()))

    total_available_hours = 40 - total_weekly_hours['hours_sum']

    time_form = TimeForm(initial={'ts_date': today})
    expense_form = ExpenseForm(initial={'ts_date': today})
    edit_time_form = EditTimeForm()
    editExpForm = EditExpenseForm()
    if request.method == 'POST':
        if 'submit_button' in request.POST:
            for entry in employee_ts_entries:
                    entry.submitted_on = today
                    entry.save()
            employee_instance = get_object_or_404(Employee, user=request.user.id)
            employee_instance.ts_is_submitted = True
            employee_instance.save()
            return redirect('dashboard')
        elif 'time_button' in request.POST:
            time_form = TimeForm(request.POST, initial={'ts_date': today})
            if time_form.is_valid():
                engagement_id = request.POST.get('engagement-input')
                engagement_instance = get_object_or_404(Engagement, engagement_srg_id=engagement_id)

                employee_instance = get_object_or_404(Employee, user=request.user.id)

                new_entry = time_form.save(commit=False)
                new_entry.employee_id = employee_instance.employee_id
                new_entry.engagement = engagement_instance
                new_entry.ts_period = last_week_end
                new_entry.save()

                if engagement_instance.alert:
                    engagement_hours = Time.objects.filter(engagement=engagement_instance.engagement_id).aggregate(
                        ehours=Sum('hours')
                    )

                    if engagement_instance.budget_hours - engagement_hours['ehours'] <= 0:
                        overBudgetAlert(engagement_instance.engagement_id)

                return redirect('employee-timesheet-review')
        elif 'expense_button' in request.POST:
            expense_form = ExpenseForm(request.POST, initial={'ts_date': today})
            if expense_form.is_valid():
                employee_instance = get_object_or_404(Employee, user=request.user.id)
                engagement_id = request.POST.get('expense-input')
                engagement_instance = get_object_or_404(Engagement, engagement_srg_id=engagement_id)

                new_expense = expense_form.save(commit=False)
                new_expense.employee = employee_instance
                new_expense.engagement = engagement_instance

                new_expense.save()

                return redirect('employee-timesheet-review')
    else:
        time_form = TimeForm(initial={'ts_date': today})
        expense_form = ExpenseForm()

    context = {'user_info': user_info, 'page_title': 'Submit Timesheet', 'today': today, 'last_week_beg': last_week_beg,
               'last_week_end': last_week_end, 'week_beg': last_week_beg, 'week_end': last_week_end,
               'current_week': current_week, 'employee_ts_entries': employee_ts_entries,
               'ts_is_submitted': ts_is_submitted, 'editExpForm': editExpForm,
               'total_weekly_expenses': total_weekly_expenses,
               'employee_hours_by_day': employee_hours_by_day, 'user_engagements': user_engagements,
               'total_weekly_hours': total_weekly_hours, 'total_available_hours': total_available_hours,
               'time_form': time_form, 'edit_time_form': edit_time_form, 'expense_form': expense_form
               }

    return render(request, 'employeeTimesheetReview.html', context)


def EmployeeTimesheet(request):
    user_info = get_object_or_404(User, pk=request.user.id)
    ts_is_submitted = user_info.employee.ts_is_submitted
    today = date.today()
    week_beg = today - timedelta(days=today.weekday()) - timedelta(days=1)
    week_end = week_beg + timedelta(days=6)
    # user_engagements = user_assignments.filter(employee_id=request.user.employee.employee_id)

    # user_assignments = Assignments.objects.filter(employee_id=user_info.employee.employee_id).values(
    # 'engagement_id') user_engagements = Engagement.objects.filter(engagement_id__in=user_assignments).order_by(
    # '-fye', 'time_code', 'parent_id')

    user_engagements = Engagement.objects.select_related().filter(
        is_complete=False, assignments__employee__employee_id=user_info.employee.employee_id).order_by('provider_id')
    # user_engagements = user_engagements.filter(assignments__employee__employee_id=user_info.employee.employee_id)

    employee_ts_entries = Time.objects.filter(employee__user__username=request.user.username).filter(
        ts_date__gte=week_beg).filter(ts_date__lte=week_end).order_by('ts_date')

    employee_hours_by_day = employee_ts_entries.values('ts_date').annotate(ts_hours=Sum('hours'))

    total_weekly_hours = employee_ts_entries.aggregate(hours_sum=Coalesce(Sum('hours'), 0, output_field=DecimalField()))

    employee_weekly_expenses = Expense.objects.values('expense_id', 'engagement__provider',
                                                      'engagement__provider__provider_name',
                                                      'engagement__time_code',
                                                      'engagement__time_code__time_code_desc',
                                                      'expense_category__expense_category',
                                                      'expense_amount',
                                                      'time_type_id').filter(employee=request.user.employee).filter(
        date__gte=week_beg).filter(date__lte=week_end).order_by('date')

    total_weekly_expenses = employee_weekly_expenses.aggregate(
        expense_sum=Coalesce(Sum('expense_amount'), 0, output_field=DecimalField()))

    total_available_hours = 40 - total_weekly_hours['hours_sum']

    current_week = []
    current_week_ts = {}

    for i in range(7):
        current_week.append(week_beg + timedelta(days=i))

    edit_time_form = EditTimeForm()
    time_form = TimeForm(request.POST, initial={'ts_date': today})
    expense_form = ExpenseForm(request.POST, initial={'ts_date': today})
    editExpForm = EditExpenseForm()
    if request.method == 'POST':
        if 'time_button' in request.POST:
            time_form = TimeForm(request.POST, initial={'ts_date': today})
            print("TIME BUTTON PRESSED")
            if time_form.is_valid():
                engagement_id = request.POST.get('engagement-input')
                engagement_instance = get_object_or_404(Engagement, engagement_srg_id=engagement_id)

                employee_instance = get_object_or_404(Employee, user=request.user.id)

                new_entry = time_form.save(commit=False)
                new_entry.employee_id = employee_instance.employee_id
                new_entry.engagement = engagement_instance
                new_entry.ts_period = week_end
                new_entry.save()

                if engagement_instance.alert:
                    engagement_hours = Time.objects.filter(engagement=engagement_instance.engagement_id).aggregate(
                        ehours=Sum('hours')
                    )

                    if (engagement_instance.budget_amount // 200) - engagement_hours['ehours'] <= 0:
                        overBudgetAlert(engagement_instance.engagement_id)

                return redirect('employee-timesheet')
            else:
                print("Form Errors:", time_form.errors)
        elif 'expense_button' in request.POST:
            expense_form = ExpenseForm(request.POST, initial={'ts_date': today})
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
        time_form = TimeForm(initial={'ts_date': today})
        expense_form = ExpenseForm()

    context = {'today': today, 'page_title': 'Timesheet', 'employee_ts_entries': employee_ts_entries,
               'week_beg': week_beg, 'week_end': week_end, 'ts_is_submitted': ts_is_submitted,
               'current_week': current_week, 'current_week_ts': current_week_ts, 'user_engagements': user_engagements,
               'time_form': time_form, 'expense_form': expense_form, 'edit_time_form': edit_time_form,
               'total_weekly_hours': total_weekly_hours, 'user_info': user_info,
               'total_available_hours': total_available_hours, 'editExpForm': editExpForm,
               'total_weekly_expenses': total_weekly_expenses,
               'employee_weekly_expenses': employee_weekly_expenses,
               'employee_hours_by_day': employee_hours_by_day}

    return render(request, 'employeeTimesheet.html', context)


def EmployeeTodolist(request):
    user_info = get_object_or_404(User, pk=request.user.id)
    ts_is_submitted = user_info.employee.ts_is_submitted
    today = date.today()
    week_beg = today - timedelta(days=today.weekday()) - timedelta(days=1)
    week_end = week_beg + timedelta(days=5)
    # user_assignments = Assignments.objects.filter(employee_id=user_info.employee.employee_id).values('engagement_id')
    # user_engagements = Engagement.objects.filter(engagement_id__in=user_assignments)
    user_engagements = Engagement.objects.select_related().filter(is_complete=False,
                                                                  assignments__employee__employee_id=user_info.employee.employee_id).order_by(
        'provider_id')

    employee_td_entries = Todolist.objects.select_related('engagement').filter(
        employee__user__username=user_info.username).filter(
        todo_date__gte=week_beg).order_by('todo_date')

    employee_td_hours_by_day = employee_td_entries.values('todo_date').annotate(
        total_day_td_hours=Sum('anticipated_hours'))

    current_week = []
    current_week_ts = {}

    for i in range(28):
        current_week.append(week_beg + timedelta(days=i))

    paginator = Paginator(current_week, 7)

    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    edit_todo_form = EditTodoForm()
    if request.method == 'POST':
        todo_form = TodoForm(request.POST)
        if todo_form.is_valid():
            engagement_id = request.POST.get('engagement-input')
            engagement_instance = get_object_or_404(Engagement, engagement_srg_id=engagement_id)
            employee_instance = get_object_or_404(Employee, user=request.user.id)

            start_date = request.POST.get('todo_date')
            start_date = datetime.strptime(start_date, "%Y-%m-%d")
            end_date = request.POST.get('todo_date_end')
            end_date = datetime.strptime(end_date, "%Y-%m-%d")

            # start_date = todo_form.cleaned_data.get('todo_date')
            # end_date = todo_form.cleaned_data.get('todo_date_end')

            number_of_days = (end_date - start_date)

            if number_of_days.days == 0:
                new_entry = todo_form.save(commit=False)
                new_entry.employee_id = employee_instance.employee_id
                new_entry.engagement = engagement_instance
                new_entry.todo_date_end = start_date
                new_entry.save()
            elif number_of_days.days > 0:
                number_of_days = number_of_days + timedelta(days=1)
                for i in range(0, number_of_days.days):
                    new_entry = Todolist(
                        employee=employee_instance,
                        engagement=engagement_instance,
                        todo_date=start_date + timedelta(days=i),
                        todo_date_end=start_date + timedelta(days=i),
                        anticipated_hours=request.POST.get('anticipated_hours'),
                        note=request.POST.get('note')
                    )
                    # new_entry.todo_date = start_date + timedelta(days=i)
                    # new_entry.todo_date_end = start_date + timedelta(days=i)
                    # new_entry.employee_id = employee_instance.employee_id
                    # new_entry.engagement = engagement_instance
                    new_entry.save()
            else:
                pass
            return redirect('employee-todolist')
    else:
        todo_form = TodoForm()

    context = {'page_title': 'To-Do List', 'week_beg': week_beg, 'ts_is_submitted': ts_is_submitted,
               'week_end': week_end, 'today': today, 'employee_td_entries': employee_td_entries,
               'todo_form': todo_form, 'user_info': user_info, 'page_obj': page_obj, 'paginator': paginator,
               'employee_td_hours_by_day': employee_td_hours_by_day, 'edit_todo_form': edit_todo_form,
               'current_week': current_week, 'current_week_ts': current_week_ts, 'user_engagements': user_engagements}

    return render(request, 'employeeTodolist.html', context)


def EmployeeExpense(request):
    user_info = get_object_or_404(User, pk=request.user.id)
    today = date.today()
    week_beg = today - timedelta(days=today.weekday()) - timedelta(days=1)
    week_end = week_beg + timedelta(days=6)
    edit_exp_form = EditExpenseForm()

    # current_employee = get_object_or_404(Employee, user_id=request.user.id)
    employee_expenses = Expense.objects.filter(employee__user__username=request.user.username).filter(
        date__gte=week_beg).filter(date__lte=week_end).order_by('date')

    total_expense = employee_expenses.aggregate(Sum('expense_amount'))

    queryset = Expense.objects.none()

    if request.GET:
        queryset = Expense.objects.values('expense_id',
                                          'date',
                                          'employee__user__username',
                                          'engagement__engagement_srg_id',
                                          'engagement__parent__parent_name',
                                          'engagement__provider',
                                          'engagement__provider__provider_name',
                                          'engagement__time_code',
                                          'engagement__time_code__time_code_desc',
                                          'engagement__fye',
                                          'expense_category__expense_category',
                                          'time_type_id',
                                          'expense_amount').order_by('date', 'engagement__parent__parent_name',
                                                                     'engagement__provider', 'engagement__fye').filter(
            employee_id=user_info.employee)

    f = ExpenseFilter(request.GET, queryset=queryset)
    qs = f.qs

    qs_expense_total = qs.aggregate(expense_sum=Sum('expense_amount'))

    context = {'employee_expenses': employee_expenses, 'week_beg': week_beg, 'week_end': week_end,
               'edit_exp_form': edit_exp_form, 'total_expense': total_expense, 'user_info': user_info,
               'page_title': 'Expense Report', 'today': today, 'filter': f, 'qs_expense_total': qs_expense_total}

    return render(request, 'employeeExpense.html', context)


def CheckDateRange(request, beg_range, end_range):
    if request.method == 'POST':
        ts_date = request.POST.get('ts_date')
        print(ts_date)
        if not ts_date:
            return JsonResponse({'error': 'No date selected.'}, status=400)

        try:
            ts_date_obj = datetime.strptime(ts_date, "%Y-%m-%d")
            beg_range_obj = datetime.strptime(beg_range, "%Y-%m-%d")
            end_range_obj = datetime.strptime(end_range, "%Y-%m-%d")

            if ts_date_obj < beg_range_obj or ts_date_obj > end_range_obj:
                return JsonResponse({'show_modal': True, 'message': 'Date is out of range, please confirm'})
            else:
                return JsonResponse({'show_modal': False})
        except ValueError:
            return JsonResponse({'error': 'Invalid date format.'}, status=400)

    return JsonResponse({'error': 'Invalid request method.'}, status=405)


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

    return redirect('engagement-detail', pk)


def ToggleEngagementAlerts(request, pk):
    engagement_instance = get_object_or_404(Engagement, pk=pk)
    if engagement_instance.alert is False:
        engagement_instance.alert = True
        engagement_instance.save()
    else:
        engagement_instance.alert = False
        engagement_instance.save()

    return redirect('engagement-detail', pk)


def AssignmentProjects(request, pk):
    user_info = get_object_or_404(User, pk=request.user.id)
    engagement_instance = get_object_or_404(Engagement, pk=pk)
    today = date.today()
    week_beg = today - timedelta(days=today.weekday()) - timedelta(days=1)
    week_end = week_beg + timedelta(days=6)

    eid = engagement_instance.engagement_id
    engagement_assignments = Assignments.objects.filter(engagement=engagement_instance).order_by('employee__user')

    available_staff = Employee.objects.exclude(
        employee_id__in=engagement_assignments.values('employee_id').filter(engagement=eid)
    ).order_by('user__first_name')

    # available_staff = available_staff

    context = {'engagement_assignments': engagement_assignments, 'engagement_instance': engagement_instance,
               'available_staff': available_staff, 'user_info': user_info, 'week_beg': week_beg, 'week_end': week_end,
               'today': today, 'page_title': 'Assign Staff'}

    return render(request, 'assign.html', context)


def AddAssignment(request, eng, emp):
    engagement_instance = get_object_or_404(Engagement, pk=eng)
    employee_instance = get_object_or_404(Employee, pk=emp)

    new_assignment = Assignments(engagement=engagement_instance, employee=employee_instance)
    new_assignment.save()

    return redirect('admin-assign', eng)


def BulkAddAssignment(request, eng, emp):
    engagement_instance = get_object_or_404(Engagement, pk=eng)
    employee_instance = get_object_or_404(Employee, pk=emp)

    if Assignments.objects.filter(engagement=eng, employee=emp).exists():
        pass
    else:
        new_assignment = Assignments.objects.create(engagement=engagement_instance, employee=employee_instance)
        new_assignment.save()

    return redirect('admin-assignments')


def RemoveAssignment(request, eng, emp):
    engagement_instance = get_object_or_404(Engagement, pk=eng)
    employee_instance = get_object_or_404(Employee, pk=emp)
    assignment_instance = get_object_or_404(Assignments, employee=emp, engagement=engagement_instance)

    assignment_instance.delete()

    return redirect('admin-assign', eng)


def DeleteTimesheetEntry(request, pk):
    entry_instance = get_object_or_404(Time, pk=pk)
    entry_instance.delete()

    return redirect('employee-timesheet')


def DeleteRevTimesheetEntry(request, pk):
    entry_instance = get_object_or_404(Time, pk=pk)
    entry_instance.delete()

    return redirect('employee-timesheet-review')


def GetTsEntry(request, ts_id):
    entry = Time.objects.get(pk=ts_id)
    data = {
        'ts_id': entry.timesheet_id,
        'engagement': entry.engagement_id,
        'ts_date': entry.ts_date,
        'hours': entry.hours,
        'btype': entry.time_type_id_id,
        'note': entry.note
    }

    return JsonResponse(data)


def UpdateTsEntry(request):
    if request.method == 'POST':
        form = EditTimeForm(request.POST)
        if form.is_valid():
            entry = Time.objects.get(pk=request.POST.get('ts-id-input'))
            entry.engagement = form.cleaned_data['engagement']
            entry.ts_date = form.cleaned_data['ts_date']
            entry.hours = form.cleaned_data['hours']
            entry.time_type_id = form.cleaned_data['time_type_id']
            entry.note = form.cleaned_data['note']
            entry.save()
    return redirect('employee-timesheet')


def UpdateRevTsEntry(request):
    if request.method == 'POST':
        form = EditTimeForm(request.POST)
        if form.is_valid():
            entry = Time.objects.get(pk=request.POST.get('ts-id-input'))
            entry.engagement = form.cleaned_data['engagement']
            entry.ts_date = form.cleaned_data['ts_date']
            entry.hours = form.cleaned_data['hours']
            entry.time_type_id = form.cleaned_data['time_type_id']
            entry.note = form.cleaned_data['note']
            entry.save()
    return redirect('employee-timesheet-review')


def DeleteTdEntry(request, pk):
    entry_instance = get_object_or_404(Todolist, pk=pk)
    entry_instance.delete()

    return redirect('employee-todolist')


def DeleteEngagementNote(request, pk):
    engagement_note_instance = get_object_or_404(EngagementNotes, pk=pk)
    engagement_note_instance.delete()

    return redirect('engagement-detail', engagement_note_instance.engagement_id)


def GetExpenseEntry(request, expense_id):
    entry = Expense.objects.get(pk=expense_id)
    data = {
        'expense_id': entry.expense_id,
        'expense_date': entry.date,
        'expense_amount': entry.expense_amount,
        'engagement': entry.engagement_id,
        'category': entry.expense_category_id,
        'btype': entry.time_type_id_id,
        'note': entry.expense_note
    }

    return JsonResponse(data)


def UpdateExpenseEntry(request):
    if request.method == 'POST':
        form = EditExpenseForm(request.POST)
        if form.is_valid():
            entry = Expense.objects.get(pk=request.POST.get('expense-id-input'))
            entry.date = form.cleaned_data['date']
            entry.engagement = form.cleaned_data['engagement']
            entry.expense_category = form.cleaned_data['expense_category']
            entry.expense_amount = form.cleaned_data['expense_amount']
            entry.time_type_id = form.cleaned_data['time_type_id']
            entry.expense_note = form.cleaned_data['expense_note']
            entry.save()
    return redirect('employee-expenses')


def RevUpdateExpenseEntry(request):
    if request.method == 'POST':
        form = EditExpenseForm(request.POST)
        if form.is_valid():
            entry = Expense.objects.get(pk=request.POST.get('exp-id-input'))
            print(request.POST.get('exp-id-input'))
            entry.date = form.cleaned_data['date']
            entry.engagement = form.cleaned_data['engagement']
            entry.expense_category = form.cleaned_data['expense_category']
            entry.expense_amount = form.cleaned_data['expense_amount']
            entry.time_type_id = form.cleaned_data['time_type_id']
            entry.expense_note = form.cleaned_data['expense_note']
            entry.save()
    return redirect('employee-timesheet-review')


def CurUpdateExpenseEntry(request):
    if request.method == 'POST':
        form = EditExpenseForm(request.POST)
        if form.is_valid():
            entry = Expense.objects.get(pk=request.POST.get('exp-id-input'))
            print(request.POST.get('exp-id-input'))
            entry.date = form.cleaned_data['date']
            entry.engagement = form.cleaned_data['engagement']
            entry.expense_category = form.cleaned_data['expense_category']
            entry.expense_amount = form.cleaned_data['expense_amount']
            entry.time_type_id = form.cleaned_data['time_type_id']
            entry.expense_note = form.cleaned_data['expense_note']
            entry.save()
    return redirect('employee-timesheet')


def DeleteExpenseEntry(request, pk):
    entry_instance = get_object_or_404(Expense, pk=pk)
    entry_instance.delete()
    return redirect('employee-expenses')


def CurDeleteExpenseEntry(request, pk):
    entry_instance = get_object_or_404(Expense, pk=pk)
    entry_instance.delete()
    return redirect('employee-timesheet')


def RevDeleteExpenseEntry(request, pk):
    entry_instance = get_object_or_404(Expense, pk=pk)
    entry_instance.delete()
    return redirect('employee-timesheet-review')


def GetExpenseDayList(request, dte):
    expenseDayList = list(
        Expense.objects.values('expense_id', 'engagement__provider', 'engagement__provider__provider_name',
                               'engagement__time_code', 'engagement__time_code__time_code_desc',
                               'expense_category__expense_category', 'expense_amount', 'time_type_id').filter(
            employee=request.user.employee).filter(date=dte)
    )
    return JsonResponse(expenseDayList, safe=False)


def GetTdDayList(request, dte):
    tdDayList = list(
        Todolist.objects.values('todolist_id', 'engagement__provider', 'engagement__provider__provider_name',
                                'engagement__time_code', 'engagement__time_code__time_code_desc',
                                'engagement__fye', 'anticipated_hours').filter(
            employee=request.user.employee).filter(todo_date=dte))
    # tdDayListJson = serializers.serialize('json', tdDayList)
    return JsonResponse(tdDayList, safe=False)


def AdminGetTdDayList(request, dte, emp_id):
    AdminTdDayList = list(
        Todolist.objects.values('todolist_id', 'engagement__provider', 'engagement__provider__provider_name',
                                'engagement__time_code', 'engagement__time_code__time_code_desc',
                                'engagement__fye', 'anticipated_hours').filter(
            employee=emp_id).filter(todo_date=dte))
    # tdDayListJson = serializers.serialize('json', tdDayList)
    return JsonResponse(AdminTdDayList, safe=False)


def GetTdWeekList(request, week_beg, week_end):
    tdWeekList = list(
        Todolist.objects.values('todolist_id', 'todo_date', 'engagement__provider',
                                'engagement__provider__provider_name',
                                'engagement__time_code', 'engagement__time_code__time_code_desc',
                                'engagement__fye', 'anticipated_hours').filter(
            employee=request.user.employee).filter(todo_date__gte=week_beg, todo_date__lte=week_end).order_by(
            'todo_date'))
    return JsonResponse(tdWeekList, safe=False)


def AdminGetTdWeekList(request, week_beg, week_end, emp_id):
    adminTdWeekList = list(
        Todolist.objects.values('todolist_id', 'todo_date', 'engagement__provider',
                                'engagement__provider__provider_name',
                                'engagement__time_code', 'engagement__time_code__time_code_desc',
                                'engagement__fye', 'anticipated_hours').filter(
            employee=emp_id).filter(todo_date__gte=week_beg, todo_date__lte=week_end).order_by(
            'todo_date'))
    return JsonResponse(adminTdWeekList, safe=False)


def GetTdEntry(request, td_id):
    entry = Todolist.objects.get(pk=td_id)
    entry = get_object_or_404(Todolist, pk=td_id)
    provider_number = entry.engagement.provider_id
    provider_name = entry.engagement.provider.provider_name
    time_code = entry.engagement.time_code_id
    time_code_desc = entry.engagement.time_code.time_code_desc
    todo_date = datetime.strptime(str(entry.todo_date), '%Y-%m-%d')
    todo_date_formatted = todo_date.strftime('%m/%d/%Y')
    if entry.engagement.fye is None:
        fiscal_year_formatted = "N/A"
    else:
        fiscal_year = datetime.strptime(str(entry.engagement.fye), '%Y-%m-%d')
        fiscal_year_formatted = fiscal_year.strftime('%m/%d/%Y')
    data = {
        'td_id': entry.todolist_id,
        'engagement': entry.engagement_id,
        'provider_number': provider_number,
        'provider_name': provider_name,
        'time_code': time_code,
        'time_code_desc': time_code_desc,
        'todo_date_formatted': todo_date_formatted,
        'todo_date': entry.todo_date,
        'todo_date_end': entry.todo_date_end,
        'fiscal_year': fiscal_year_formatted,
        'anticipated_hours': entry.anticipated_hours,
        'note': entry.note
    }
    return JsonResponse(data)


def UpdateTdEntry(request):
    if request.method == 'POST':
        form = EditTodoForm(request.POST)
        if form.is_valid():
            entry = Todolist.objects.get(pk=request.POST.get('td-id-input'))
            entry.engagement = form.cleaned_data['engagement']
            entry.todo_date = form.cleaned_data['todo_date']
            entry.todo_date_end = form.cleaned_data['todo_date_end']
            entry.anticipated_hours = form.cleaned_data['anticipated_hours']
            entry.note = form.cleaned_data['note']
            entry.save()
    return redirect('employee-todolist')


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
    engagement_scope = str(engagement_instance.time_code)
    engagement_fye = str(engagement_instance.fye)

    msg = EmailMessage(
        from_email='Randall.Gienko@srgroupllc.com',
        to=['Randall.Gienko@srgroupllc.com', 'Trahan.Whitten@srgroupllc.com']
    )

    protocol = 'https://'
    engagement_url = 'tetd.azurewebsites.net/engagement-detail/' + str(engagement_instance.engagement_id) + '/'

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


class PasswordResetToken(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        return (
                six.text_type(user.pk) + six.text_type(timestamp)
        )


def ForgotPassword(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        print(email)
        # password = request.POST.get('password')
        user = get_object_or_404(User, email=email)
        if user is not None:
            return redirect('forgot-password-done', user.id)
        else:
            messages.error(request, 'User does not exists, please confirm email.')
    else:
        return render(request, 'registration/password_reset_form.html')


def ForgotPassDone(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user is not None:
        send_password_reset_email(request, user.id)
    return render(request, 'registration/password_reset_done.html')


def send_password_reset_email(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    # sg = sendgrid.SendGridAPIClient(api_key=os.environ.get('SENDGRID_API_KEY'))
    template_id = 'd-ba0cc16816a94181acce7efe0761c14b'

    # timestamp = int(time.mktime(datetime.now().timetuple()))
    # token_generator = PasswordResetToken()
    token = default_token_generator.make_token(user)
    reset_link = request.build_absolute_uri(
        reverse('forgot-password-confirm', kwargs={'uidb64': str(user_id), 'token': str(token)})
    )

    msg = EmailMessage(
        from_email='Randall.Gienko@srgroupllc.com',
        to=[user.email]
    )

    msg.template_id = template_id
    msg.dynamic_template_data = {
        "user_email": user.email,
        "reset_link": reset_link
    }

    # msg.SendGridAPIClient(SENDGRID_API_KEY)
    msg.send(fail_silently=False)
    # sg = SendGridAPIClient(SENDGRID_API_KEY)
    # response = sg.send(msg)


def ForgotPassConfirm(request, uidb64, token):
    form = UserPasswordResetForm(request.POST)

    if request.method == 'POST':
        try:
            uid = str(uidb64)
            print(uid)
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist) as e:
            messages.add_message(request, messages.WARNING, str(e))
            user = None

        if user is not None and default_token_generator.check_token(user, token):
            form = UserPasswordResetForm(user=user, data=request.POST)
            if form.is_valid():
                form.save()
                update_session_auth_hash(request, form.user)

                user.is_active = True
                user.save()
                messages.add_message(request, messages.SUCCESS, 'Password reset successfully.')
                return redirect('login')
            else:
                context = {
                    'form': form,
                    'uid': str(uidb64),
                    'token': token
                }
                messages.add_message(request, messages.WARNING, 'Password could not be reset.')
                return render(request, 'registration/password_reset_conf.html', context)
        else:
            messages.add_message(request, messages.WARNING, 'Password reset link is invalid.')
            messages.add_message(request, messages.WARNING, 'Please request a new password reset.')

    try:
        uid = str(uidb64)
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist) as e:
        messages.add_message(request, messages.WARNING, str(e))
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        context = {
            'form': UserPasswordResetForm(user),
            'uid': str(uidb64),
            'token': token
        }
        return render(request, 'registration/password_reset_conf.html', context)
    else:
        messages.add_message(request, messages.WARNING, 'Password reset link is invalid.')
        messages.add_message(request, messages.WARNING, 'Please request a new password reset.')

    context = {'password_reset_form': form}
    return render(request, 'login.html', context)


def createEmployeeHoursCompilationReport(request, mnth):
    global period
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Justify', alignment=TA_LEFT))
    # title = Paragraph('<para>Strategic Reimbursement Group, LLC</para>', styles['Normal'])
    # subTitle = Paragraph('<para>Productivity Hours Report</para>', styles['Normal'])
    if mnth == "YTD":
        period_text = Paragraph('<para>Year To Date</para>', styles['Normal'])
        period = "YTD"
    else:
        period_date = datetime.strptime(mnth, "%Y-%m-%d")
        period_text = Paragraph('<para>' + str(period_date.strftime("%B")) + " " + str(period_date.year) + '</para>')
        period = period_date.month
        print(period)
    vps = Employee.objects.filter(title='VP', is_billable=True).values('employee_id', 'user__username', 'user__last_name', 'user__first_name').order_by('user__last_name')
    smgrs = Employee.objects.filter(title='SM', is_billable=True).values('employee_id', 'user__username', 'user__last_name', 'user__first_name').order_by('user__last_name')
    mgrs = Employee.objects.filter(title='M', is_billable=True).values('employee_id', 'user__username', 'user__last_name', 'user__first_name').order_by('user__last_name')
    cs = Employee.objects.filter(Q(title='SC', is_billable=True) | Q(title='C', is_billable=True)).values('employee_id', 'user__username', 'user__last_name', 'user__first_name').order_by(
        'user__last_name')

    tblStyleWithHeader = TableStyle([('BOX', (0, 0), (-1, -1), 1, colors.black),
                                     ('INNERGRID', (0, 0), (-1, -1), 1, colors.black),
                                     ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                                     ('BACKGROUND', (0, 0), (-1, 0), colors.yellow)])

    tblStyle = TableStyle([('BOX', (0, 0), (-1, -1), 1, colors.black),
                           ('INNERGRID', (0, 0), (-1, -1), 1, colors.black),
                           ('ALIGN', (0, 0), (-1, -1), 'CENTER')])

    total_row_style = TableStyle([('BOX', (0, 0), (-1, -1), 1, colors.black),
                                  ('INNERGRID', (0, 0), (-1, -1), 1, colors.black)])

    blank_row_style = TableStyle([('BOX', (0, 0), (-1, -1), 1, colors.black),
                                  ('INNERGRID', (0, 0), (-1, -1), 1, colors.black),
                                  ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#d9d9d9'))])

    elements = [period_text]
    spacer = Spacer(1, 20)
    elements.append(spacer)

    # Create Column Headers for Table #
    employeeHeader = Paragraph('<para align=center>Employee</para>', styles['Normal'])
    fixedHeader = Paragraph('<para align=center>Fixed</para>', styles['Normal'])
    hourlyHeader = Paragraph('<para align=center>Hourly</para>', styles['Normal'])
    cgyHeader = Paragraph('<para align=center>CGY</para>', styles['Normal'])
    nbHeader = Paragraph('<para align=center>NB</para>', styles['Normal'])
    ptoHeader = Paragraph('<para align=center>PTO</para>', styles['Normal'])
    billableHeader = Paragraph('<para align=center>Total Billable<br/>with<br/>Contingency</para>', styles['Normal'])
    totalHeader = Paragraph('<para align=center>Total with<br/>Non-Billable</para>', styles['Normal'])
    percentBillableHeader = Paragraph('<para align=center>% Billable</para>', styles['Normal'])

    data = [[employeeHeader, fixedHeader, hourlyHeader, cgyHeader, nbHeader, ptoHeader, billableHeader, totalHeader,
             percentBillableHeader]]

    header_row = Table(data, colWidths=[4 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm,
                                        2.5 * cm, 2.5 * cm, 2 * cm])
    header_row.setStyle(tblStyleWithHeader)
    elements.append(header_row)

    compilationData = getCompilationData(period)

    billable_weeks_per_month = compilationData[69]
    billable_hours_per_month = compilationData[68] * 8

    vp_fixed = compilationData[0]
    vp_hourly = compilationData[1]
    vp_cgy = compilationData[2]
    vp_nb = compilationData[3]
    vp_pto = compilationData[4]
    vp_billable = compilationData[5]
    vp_total = compilationData[6]

    vp_data_row_data = []

    for emp in vps:
        employeeColumn = Paragraph('<para align=left>' + str(emp['user__last_name']) + ', ' + str(emp['user__first_name']) + '</para>', styles['Normal'])
        employeePercentBillableColumn = 0
        employeeHourlyColumn = 0
        employeeFixedColumn = 0
        employeeCGYColumn = 0
        employeeNBColumn = 0
        employeePTOColumn = 0
        employeeBillableColumn = 0
        employeeTotalColumn = 0
        percentBillable = 0
        for item in vp_fixed:
            if item['employee_id'] == emp['employee_id']:
                employeeFixedColumn = Paragraph(
                    '<para align=center>' + str(item['fixed_hours_by_employee_sum']) + '</para>')
        for item in vp_hourly:
            if item['employee_id'] == emp['employee_id']:
                employeeHourlyColumn = Paragraph(
                    '<para align=center>' + str(item['hourly_hours_by_employee_sum']) + '</para>',
                    styles['Normal'])
        for item in vp_cgy:
            if item['employee_id'] == emp['employee_id']:
                employeeCGYColumn = Paragraph(
                    '<para align=center>' + str(item['cgy_hours_by_employee_sum']) + '</para>', styles['Normal'])
        for item in vp_nb:
            if item['employee_id'] == emp['employee_id']:
                employeeNBColumn = Paragraph('<para align=center>' + str(item['non_billable_hours_sum']) + '</para>',
                                             styles['Normal'])
        for item in vp_pto:
            if item['employee_id'] == emp['employee_id']:
                employeePTOColumn = Paragraph(
                    '<para align=center>' + str(item['pto_hours_by_employee_sum']) + '</para>', styles['Normal'])
        for item in vp_billable:
            if item['employee_id'] == emp['employee_id']:
                percentBillable = round((item['billable_hours_sum'] / billable_hours_per_month) * 100, 2)
                employeeBillableColumn = Paragraph(
                    '<para align=center><b>' + str(item['billable_hours_sum']) + '</b></para>',
                    styles['Normal'])
        for item in vp_total:
            if item['employee_id'] == emp['employee_id']:
                employeeTotalColumn = Paragraph('<para align=center><b>' + str(item['total_hours_sum']) + '</b></para>',
                                                styles['Normal'])

        employeePercentBillableColumn = Paragraph('<para align=center><b>' + str(percentBillable) + '%</b></para>',
                                                  styles['Normal'])

        vp_data_row_data.append([employeeColumn, employeeFixedColumn, employeeHourlyColumn,
                                 employeeCGYColumn, employeeNBColumn, employeePTOColumn, employeeBillableColumn,
                                 employeeTotalColumn, employeePercentBillableColumn])

    vp_data_row = Table(vp_data_row_data, repeatRows=1,
                        colWidths=[4 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm,
                                   2.5 * cm, 2.5 * cm, 2 * cm])
    vp_data_row.hAlign = 'CENTER'
    vp_data_row.setStyle(tblStyle)
    elements.append(vp_data_row)

    vp_total_data = []

    vp_total_text = Paragraph('')
    vp_fixed_total_column = Paragraph('<para align=center><b>' + str(compilationData[7]['amount']) + '</b></para>')
    vp_hourly_total = Paragraph('<para align=center><b>' + str(compilationData[8]['amount']) + '</b></para>')
    vp_cgy_total = Paragraph('<para align=center><b>' + str(compilationData[9]['amount']) + '</b></para>')
    vp_nb_total = Paragraph('<para align=center><b>' + str(compilationData[10]['amount']) + '</b></para>')
    vp_pto_total = Paragraph('<para align=center><b>' + str(compilationData[11]['amount']) + '</b></para>')
    vp_billable_total = Paragraph('<para align=center><b>' + str(compilationData[12]['amount']) + '</b></para>')
    vp_total_total = Paragraph('<para align=center><b>' + str(compilationData[13]['amount']) + '</b></para>')
    vp_percent_billable_total = Paragraph('')

    vp_total_data.append(
        [vp_total_text, vp_fixed_total_column, vp_hourly_total, vp_cgy_total, vp_nb_total, vp_pto_total,
         vp_billable_total, vp_total_total, vp_percent_billable_total])

    vp_total_row = Table(vp_total_data, colWidths=[4 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm,
                                                   2.5 * cm, 2.5 * cm, 2 * cm])
    vp_total_row.hAlign = 'CENTER'
    vp_total_row.setStyle(total_row_style)

    elements.append(vp_total_row)

    blank_row_data = ['']
    blank_row = Table(blank_row_data, colWidths=[19.75 * cm], rowHeights=[.25 * cm])
    blank_row.setStyle(blank_row_style)

    elements.append(blank_row)
    # ################################################# SR MANAGERS TABLE ##############################################
    smgr_fixed = compilationData[14]
    smgr_hourly = compilationData[15]
    smgr_cgy = compilationData[16]
    smgr_nb = compilationData[17]
    smgr_pto = compilationData[18]
    smgr_billable = compilationData[19]
    smgr_total = compilationData[20]

    smgr_data = []
    smgr_total_data = []

    smgr_total_text = Paragraph('')
    smgr_fixed_total_column = Paragraph('<para align=center><b>' + str(compilationData[21]['amount']) + '</b></para>')
    smgr_hourly_total = Paragraph('<para align=center><b>' + str(compilationData[22]['amount']) + '</b></para>')
    smgr_cgy_total = Paragraph('<para align=center><b>' + str(compilationData[23]['amount']) + '</b></para>')
    smgr_nb_total = Paragraph('<para align=center><b>' + str(compilationData[24]['amount']) + '</b></para>')
    smgr_pto_total = Paragraph('<para align=center><b>' + str(compilationData[25]['amount']) + '</b></para>')
    smgr_billable_total = Paragraph('<para align=center><b>' + str(compilationData[26]['amount']) + '</b></para>')
    smgr_total_total = Paragraph('<para align=center><b>' + str(compilationData[27]['amount']) + '</b></para>')
    smgr_percent_billable_total = Paragraph('')

    smgr_total_data.append(
        [smgr_total_text, smgr_fixed_total_column, smgr_hourly_total, smgr_cgy_total, smgr_nb_total, smgr_pto_total,
         smgr_billable_total, smgr_total_total, smgr_percent_billable_total])

    for emp in smgrs:
        smgrEmployeeFixedColumn = 0
        smgrEmployeeHourlyColumn = 0
        smgrEmployeeCGYColumn = 0
        smgrEmployeeNBColumn = 0
        smgrEmployeePTOColumn = 0
        smgrEmployeeBillableColumn = 0
        smgrEmployeeTotalColumn = 0
        smgrPercentBillable = 0
        employeeColumn = Paragraph('<para align=left>' + str(emp['user__last_name']) + ', ' + str(emp['user__first_name']) + '</para>', styles['Normal'])
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
                smgrPercentBillable = round((item['billable_hours_sum'] / billable_hours_per_month) * 100, 2)
                smgrEmployeeBillableColumn = Paragraph(
                    '<para align=center><b>' + str(item['billable_hours_sum']) + '</b></para>', styles['Normal'])
        for item in smgr_total:
            if item['employee_id'] == emp['employee_id']:
                smgrEmployeeTotalColumn = Paragraph(
                    '<para align=center><b>' + str(item['total_hours_sum']) + '</b></para>', styles['Normal'])
        smgrEmployeePercentBillableColumn = Paragraph(
            '<para align=center><b>' + str(smgrPercentBillable) + '%</b></para>',
            styles['Normal'])

        smgr_data.append([employeeColumn, smgrEmployeeFixedColumn, smgrEmployeeHourlyColumn, smgrEmployeeCGYColumn,
                          smgrEmployeeNBColumn, smgrEmployeePTOColumn, smgrEmployeeBillableColumn,
                          smgrEmployeeTotalColumn, smgrEmployeePercentBillableColumn])

    smgr_data_row = Table(smgr_data, repeatRows=1,
                          colWidths=[4 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm,
                                     2.5 * cm, 2.5 * cm, 2 * cm])
    smgr_data_row.hAlign = 'CENTER'
    smgr_data_row.setStyle(tblStyle)
    elements.append(smgr_data_row)

    smgr_total_data_row = Table(smgr_total_data, repeatRows=1,
                                colWidths=[4 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm,
                                           2.5 * cm, 2.5 * cm, 2 * cm])
    smgr_total_data_row.hAlign = 'CENTER'
    smgr_total_data_row.setStyle(tblStyle)
    elements.append(smgr_total_data_row)
    elements.append(blank_row)

    # ################################################# MANAGERS TABLE #################################################
    mgr_fixed = compilationData[28]
    mgr_hourly = compilationData[29]
    mgr_cgy = compilationData[30]
    mgr_nb = compilationData[31]
    mgr_pto = compilationData[32]
    mgr_billable = compilationData[33]
    mgr_total = compilationData[34]

    mgr_data = []
    mgr_total_data = []

    mgr_total_text = Paragraph('')
    mgr_fixed_total_column = Paragraph(
        '<para align=center><b>' + str(compilationData[35]['amount']) + '</b></para>')
    mgr_hourly_total = Paragraph('<para align=center><b>' + str(compilationData[36]['amount']) + '</b></para>')
    mgr_cgy_total = Paragraph('<para align=center><b>' + str(compilationData[37]['amount']) + '</b></para>')
    mgr_nb_total = Paragraph('<para align=center><b>' + str(compilationData[38]['amount']) + '</b></para>')
    mgr_pto_total = Paragraph('<para align=center><b>' + str(compilationData[39]['amount']) + '</b></para>')
    mgr_billable_total = Paragraph('<para align=center><b>' + str(compilationData[40]['amount']) + '</b></para>')
    mgr_total_total = Paragraph('<para align=center><b>' + str(compilationData[41]['amount']) + '</b></para>')
    mgr_percent_billable_total = Paragraph('')

    mgr_total_data.append(
        [mgr_total_text, mgr_fixed_total_column, mgr_hourly_total, mgr_cgy_total, mgr_nb_total, mgr_pto_total,
         mgr_billable_total, mgr_total_total, mgr_percent_billable_total])

    for emp in mgrs:
        employeeColumn = Paragraph('<para align=left>' + str(emp['user__last_name']) + ', ' + str(emp['user__first_name']) + '</para>', styles['Normal'])
        mgrEmployeeFixedColumn = 0
        mgrEmployeeHourlyColumn = 0
        mgrEmployeeCGYColumn = 0
        mgrEmployeeNBColumn = 0
        mgrEmployeePTOColumn = 0
        mgrEmployeeBillableColumn = 0
        mgrEmployeeTotalColumn = 0
        mgrPercentBillable = 0
        for item in mgr_fixed:
            if item['employee_id'] == emp['employee_id']:
                mgrEmployeeFixedColumn = str(item['fixed_hours_by_employee_sum'])
        for item in mgr_hourly:
            if item['employee_id'] == emp['employee_id']:
                mgrEmployeeHourlyColumn = Paragraph(
                    '<para align=center>' + str(item['hourly_hours_by_employee_sum']) + '</para>', styles['Normal'])
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
                mgrPercentBillable = round((item['billable_hours_sum'] / billable_hours_per_month) * 100, 2)
                mgrEmployeeBillableColumn = Paragraph(
                    '<para align=center><b>' + str(item['billable_hours_sum']) + '</b></para>', styles['Normal'])
        for item in mgr_total:
            if item['employee_id'] == emp['employee_id']:
                mgrEmployeeTotalColumn = Paragraph(
                    '<para align=center><b>' + str(item['total_hours_sum']) + '</b></para>', styles['Normal'])
        mgrEmployeePercentBillableColumn = Paragraph(
            '<para align=center><b>' + str(mgrPercentBillable) + '%</b></para>',
            styles['Normal'])

        mgr_data.append([employeeColumn, mgrEmployeeFixedColumn, mgrEmployeeHourlyColumn, mgrEmployeeCGYColumn,
                         mgrEmployeeNBColumn, mgrEmployeePTOColumn, mgrEmployeeBillableColumn,
                         mgrEmployeeTotalColumn, mgrEmployeePercentBillableColumn])

    mgr_data_row = Table(mgr_data, colWidths=[4 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm,
                                              2.5 * cm, 2.5 * cm, 2 * cm])
    mgr_data_row.hAlign = 'CENTER'
    mgr_data_row.setStyle(tblStyle)
    elements.append(mgr_data_row)

    mgr_total_data_row = Table(mgr_total_data,
                               colWidths=[4 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm,
                                          2.5 * cm, 2.5 * cm, 2 * cm])
    mgr_total_data_row.hAlign = 'CENTER'
    mgr_total_data_row.setStyle(tblStyle)
    elements.append(mgr_total_data_row)
    elements.append(blank_row)

    # ##################################### CONSULTANT TABLE ######################################################
    c_fixed = compilationData[42]
    c_hourly = compilationData[43]
    c_cgy = compilationData[44]
    c_nb = compilationData[45]
    c_pto = compilationData[46]
    c_billable = compilationData[47]
    c_total = compilationData[48]

    c_data = []
    c_total_data = []

    c_total_text = Paragraph('')
    c_fixed_total_column = Paragraph(
        '<para align=center><b>' + str(compilationData[49]['amount']) + '</b></para>')
    c_hourly_total = Paragraph('<para align=center><b>' + str(compilationData[50]['amount']) + '</b></para>')
    c_cgy_total = Paragraph('<para align=center><b>' + str(compilationData[51]['amount']) + '</b></para>')
    c_nb_total = Paragraph('<para align=center><b>' + str(compilationData[52]['amount']) + '</b></para>')
    c_pto_total = Paragraph('<para align=center><b>' + str(compilationData[53]['amount']) + '</b></para>')
    c_billable_total = Paragraph('<para align=center><b>' + str(compilationData[54]['amount']) + '</b></para>')
    c_total_total = Paragraph('<para align=center><b>' + str(compilationData[55]['amount']) + '</b></para>')
    c_percent_billable_total = Paragraph('')

    c_total_data.append(
        [c_total_text, c_fixed_total_column, c_hourly_total, c_cgy_total, c_nb_total, c_pto_total,
         c_billable_total, c_total_total, c_percent_billable_total])

    for emp in cs:
        employeeColumn = Paragraph('<para align=left>' + str(emp['user__last_name']) + ', ' + str(emp['user__first_name']) + '</para>', styles['Normal'])
        cEmployeeFixedColumn = 0
        cEmployeeHourlyColumn = 0
        cEmployeeCGYColumn = 0
        cEmployeeNBColumn = 0
        cEmployeePTOColumn = 0
        cEmployeeBillableColumn = 0
        cEmployeeTotalColumn = 0
        cPercentBillable = 0
        for item in c_fixed:
            if item['employee_id'] == emp['employee_id']:
                cEmployeeFixedColumn = str(item['fixed_hours_by_employee_sum'])
        for item in c_hourly:
            if item['employee_id'] == emp['employee_id']:
                cEmployeeHourlyColumn = Paragraph(
                    '<para align=center>' + str(item['hourly_hours_by_employee_sum']) + '</para>', styles['Normal'])
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
                cPercentBillable = round((item['billable_hours_sum'] / billable_hours_per_month) * 100, 2)
                cEmployeeBillableColumn = Paragraph(
                    '<para align=center><b>' + str(item['billable_hours_sum']) + '</b></para>', styles['Normal'])
        for item in c_total:
            if item['employee_id'] == emp['employee_id']:
                cEmployeeTotalColumn = Paragraph(
                    '<para align=center><b>' + str(item['total_hours_sum']) + '</b></para>', styles['Normal'])
        cEmployeePercentBillableColumn = Paragraph('<para align=center><b>' + str(cPercentBillable) + '%</b></para>',
                                                   styles['Normal'])

        c_data.append([employeeColumn, cEmployeeFixedColumn, cEmployeeHourlyColumn, cEmployeeCGYColumn,
                       cEmployeeNBColumn, cEmployeePTOColumn, cEmployeeBillableColumn,
                       cEmployeeTotalColumn, cEmployeePercentBillableColumn])

    c_data_row = Table(c_data, colWidths=[4 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm,
                                          2.5 * cm, 2.5 * cm, 2 * cm])
    c_data_row.hAlign = 'CENTER'
    c_data_row.setStyle(tblStyle)
    elements.append(c_data_row)

    c_total_data_row = Table(c_total_data,
                             colWidths=[4 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm,
                                        2.5 * cm, 2.5 * cm, 2 * cm])
    c_total_data_row.hAlign = 'CENTER'
    c_total_data_row.setStyle(tblStyle)
    elements.append(c_total_data_row)
    elements.append(blank_row)

    # ##################################### GRAND TOTAL CREATE ###################################################

    total_total_data = []

    total_total_text = Paragraph('<para align=center><b>Total Hours:</b></para>')
    total_fixed_total_column = Paragraph(
        '<para align=center><b>' + str(compilationData[56]) + '</b></para>')
    total_hourly_total = Paragraph('<para align=center><b>' + str(compilationData[57]) + '</b></para>')
    total_cgy_total = Paragraph('<para align=center><b>' + str(compilationData[58]) + '</b></para>')
    total_nb_total = Paragraph('<para align=center><b>' + str(compilationData[59]) + '</b></para>')
    total_pto_total = Paragraph('<para align=center><b>' + str(compilationData[60]) + '</b></para>')
    total_billable_total = Paragraph('<para align=center><b>' + str(compilationData[61]) + '</b></para>')
    total_total_total = Paragraph('<para align=center><b>' + str(compilationData[62]) + '</b></para>')
    total_percent_billable_total = Paragraph('')

    total_total_data.append(
        [total_total_text, total_fixed_total_column, total_hourly_total, total_cgy_total, total_nb_total,
         total_pto_total,
         total_billable_total, total_total_total, total_percent_billable_total])

    # ##################################### METRICS CREATION #####################################################
    vp_rate = get_object_or_404(EmployeeTitles, pk='VP')
    smgr_rate = get_object_or_404(EmployeeTitles, pk='SM')
    mgr_rate = get_object_or_404(EmployeeTitles, pk='M')
    c_rate = get_object_or_404(EmployeeTitles, pk='C')

    vp_loss_rev = round(vp_rate.rate * compilationData[10]['amount'], 0)
    smgr_lost_rev = round(smgr_rate.rate * compilationData[24]['amount'], 0)
    mgr_lost_rev = round(mgr_rate.rate * compilationData[38]['amount'], 0)
    c_lost_rev = round(c_rate.rate * compilationData[52]['amount'], 0)
    srg_total_lost_revenue = round(vp_loss_rev + smgr_lost_rev + mgr_lost_rev + c_lost_rev, 0)

    vp_metric_row_data = []
    vp_nb_text = Paragraph('<para>VP Non-Billable</para>')
    vp_nb_hours = Paragraph('<para align=center>' + str(compilationData[10]['amount']) + '</para>')
    vp_x_text = Paragraph('<para align=center>X</para>')
    vp_rate_text = Paragraph('<para align=center>$' + str(vp_rate.rate) + '</para>')
    vp_loss_rev_text = Paragraph('<para align=center>$' + str('{:,}'.format(vp_loss_rev)) + '</para>')

    vp_metric_row_data.append([vp_nb_text, vp_nb_hours, vp_x_text, vp_rate_text, vp_loss_rev_text])

    smgr_metric_row_data = []
    smgr_nb_text = Paragraph('<para>Senior Mgr. Non-Billable</para>')
    smgr_nb_hours = Paragraph('<para align=center>' + str(compilationData[24]['amount']) + '</para>')
    smgr_x_text = Paragraph('<para align=center>X</para>')
    smgr_rate_text = Paragraph('<para align=center>$' + str(smgr_rate.rate) + '</para>')
    smgr_lost_rev_text = Paragraph('<para align=center>$' + str('{:,}'.format(smgr_lost_rev)) + '</para>')

    smgr_metric_row_data.append([smgr_nb_text, smgr_nb_hours, smgr_x_text, smgr_rate_text, smgr_lost_rev_text])

    mgr_metric_row_data = []
    mgr_nb_text = Paragraph('<para>Manager Non-Billable</para>')
    mgr_nb_hours = Paragraph('<para align=center>' + str(compilationData[38]['amount']) + '</para>')
    mgr_x_text = Paragraph('<para align=center>X</para>')
    mgr_rate_text = Paragraph('<para align=center>$' + str(mgr_rate.rate) + '</para>')
    mgr_lost_rev_text = Paragraph('<para align=center>$' + str('{:,}'.format(mgr_lost_rev)) + '</para>')

    mgr_metric_row_data.append([mgr_nb_text, mgr_nb_hours, mgr_x_text, mgr_rate_text, mgr_lost_rev_text])

    c_metric_row_data = []
    c_nb_text = Paragraph('<para>Consultant Non-Billable</para>')
    c_nb_hours = Paragraph('<para align=center>' + str(compilationData[52]['amount']) + '</para>')
    c_x_text = Paragraph('<para align=center>X</para>')
    c_rate_text = Paragraph('<para align=center>$' + str(c_rate.rate) + '</para>')
    c_lost_rev_text = Paragraph('<para align=center>$' + str('{:,}'.format(c_lost_rev)) + '</para>')

    c_metric_row_data.append([c_nb_text, c_nb_hours, c_x_text, c_rate_text, c_lost_rev_text])

    total_metric_row_data = []
    total_nb_text = Paragraph('<para>Total Lost Revenue</para>')
    total_nb_hours = Paragraph('')
    total_x_text = Paragraph('')
    total_rate_text = Paragraph('')
    total_lost_rev_text = Paragraph(
        '<para align=center color=red>$' + str('{:,}'.format(srg_total_lost_revenue)) + '</para>')

    total_metric_row_data.append([total_nb_text, total_nb_hours, total_x_text, total_rate_text, total_lost_rev_text])

    billable_weeks_row_data = []
    billable_weeks_text = Paragraph('<para>Billable Weeks</para>')
    billable_weeks_blank_c1 = Paragraph('')
    billable_weeks_blank_c2 = Paragraph('')
    billable_weeks_blank_c3 = Paragraph('')
    billable_weeks_value = Paragraph('<para align=center>' + str(billable_weeks_per_month) + '</para>')
    billable_weeks_blank_c4 = Paragraph('')
    billable_weeks_text2 = Paragraph('<para><b>Actual Billable</b></para>')
    billable_weeks_value2 = Paragraph('<para align=center><b>' + str(compilationData[61]) + '</b></para>')

    billable_weeks_row_data.append([billable_weeks_text, billable_weeks_blank_c1, billable_weeks_blank_c2,
                                    billable_weeks_blank_c3, billable_weeks_value, billable_weeks_blank_c4,
                                    billable_weeks_text2, billable_weeks_value2])

    number_of_employees = Employee.objects.filter(is_billable=True).aggregate(total_employees=Count('employee_id'))
    total_billable_hours = billable_hours_per_month * number_of_employees['total_employees']
    srg_billable_percentage = round((compilationData[61] / total_billable_hours) * 100, 0)

    times_forty_hours_week_row_data = []
    time_forty_hours_week_text = Paragraph('<para>X 40 hours / week</para>')
    time_forty_hours_week_blank_c1 = Paragraph('')
    time_forty_hours_week_blank_c2 = Paragraph('')
    time_forty_hours_week_blank_c3 = Paragraph('')
    time_forty_hours_week_value = Paragraph('<para align=center>' + str(billable_hours_per_month) + '</para>')
    time_forty_hours_week_blank_c4 = Paragraph('')
    time_forty_hours_week_text2 = Paragraph('<para align=center><b>Billable %</b></para>')
    time_forty_hours_week_value2 = Paragraph('<para align=center><b>' + str(srg_billable_percentage) + '%</b></para>')

    times_forty_hours_week_row_data.append([time_forty_hours_week_text, time_forty_hours_week_blank_c1,
                                            time_forty_hours_week_blank_c2, time_forty_hours_week_blank_c3,
                                            time_forty_hours_week_value, time_forty_hours_week_blank_c4,
                                            time_forty_hours_week_text2, time_forty_hours_week_value2
                                            ])

    number_of_employees_row_data = []
    number_of_employees_text = Paragraph('<para>X # of Employees</para>')
    number_of_employees_blank_c1 = Paragraph('')
    number_of_employees_blank_c2 = Paragraph('')
    number_of_employees_blank_c3 = Paragraph('')
    number_of_employees_value = Paragraph(
        '<para align=center>' + str(number_of_employees['total_employees']) + '</para>')

    number_of_employees_row_data.append([number_of_employees_text, number_of_employees_blank_c1,
                                         number_of_employees_blank_c2, number_of_employees_blank_c3,
                                         number_of_employees_value])

    month_total_billable_hours_row_data = []
    month_total_billable_hours_text = Paragraph('<para>Total Billable @ 100%</para>')
    month_total_billable_hours_blank = Paragraph('')
    month_total_billable_hours_value = Paragraph('<para align=center>' + str(total_billable_hours) + '</para>')

    month_total_billable_hours_row_data.append([month_total_billable_hours_text, month_total_billable_hours_blank,
                                                month_total_billable_hours_blank, month_total_billable_hours_blank,
                                                month_total_billable_hours_value])

    # ##################################### TABLE CREATION ########################################################

    blank_row_data = ['']
    blank_row = Table(blank_row_data, colWidths=[19.75 * cm], rowHeights=[.25 * cm])
    blank_row.setStyle(blank_row_style)

    total_total_row = Table(total_total_data,
                            colWidths=[4 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm,
                                       2.5 * cm, 2.5 * cm, 2 * cm])

    total_total_row.hAlign = 'CENTER'
    total_total_row.setStyle(total_row_style)

    vp_metric_row = Table(vp_metric_row_data,
                          colWidths=[4.5 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 2 * cm],
                          hAlign='LEFT')
    vp_metric_row.setStyle(tblStyle)

    smgr_metric_row = Table(smgr_metric_row_data,
                            colWidths=[4.5 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 2 * cm],
                            hAlign='LEFT')
    smgr_metric_row.setStyle(tblStyle)

    mgr_metric_row = Table(mgr_metric_row_data,
                           colWidths=[4.5 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 2 * cm],
                           hAlign='LEFT')
    mgr_metric_row.setStyle(tblStyle)

    c_metric_row = Table(c_metric_row_data,
                         colWidths=[4.5 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 2 * cm],
                         hAlign='LEFT')
    c_metric_row.setStyle(tblStyle)

    total_metric_row = Table(total_metric_row_data,
                             colWidths=[4.5 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 2 * cm],
                             hAlign='LEFT')
    total_metric_row.setStyle(tblStyle)

    billable_weeks_row = Table(billable_weeks_row_data,
                               colWidths=[4.5 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 1 * cm, 3 * cm,
                                          1.75 * cm],
                               hAlign='LEFT')
    billable_weeks_row.setStyle(tblStyle)

    times_forty_hours_week_row = Table(times_forty_hours_week_row_data,
                                       colWidths=[4.5 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 1 * cm, 3 * cm,
                                                  1.75 * cm],
                                       hAlign='LEFT')
    times_forty_hours_week_row.setStyle(tblStyle)

    number_of_employees_row = Table(number_of_employees_row_data,
                                    colWidths=[4.5 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm],
                                    hAlign='LEFT')

    number_of_employees_row.setStyle(tblStyle)

    month_total_billable_hours_row = Table(month_total_billable_hours_row_data,
                                           colWidths=[4.5 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm, 1.75 * cm],
                                           hAlign='LEFT')

    month_total_billable_hours_row.setStyle(tblStyle)

    # elements.append(vp_total_row)
    elements.append(total_total_row)
    spacer = Spacer(1, 10)
    elements.append(spacer)
    elements.append(vp_metric_row)
    elements.append(smgr_metric_row)
    elements.append(mgr_metric_row)
    elements.append(c_metric_row)
    elements.append(total_metric_row)
    spacer = Spacer(1, 10)
    elements.append(spacer)
    elements.append(billable_weeks_row)
    elements.append(times_forty_hours_week_row)
    elements.append(number_of_employees_row)
    elements.append(month_total_billable_hours_row)

    buffer = BytesIO()
    employeeHoursCompilationReportDoc = SimpleDocTemplate(buffer, pagesize=[A4[0], A4[1]], leftMargin=10,
                                                          rightMargin=15,
                                                          topMargin=15, bottomMargin=5)
    employeeHoursCompilationReportDoc.build(elements)
    pdf_value = buffer.getvalue()
    buffer.close()

    response = HttpResponse(content_type='application/pdf')
    response.write(pdf_value)
    response['Content-Disposition'] = 'attachment; fileName="Productivity Hours Report.pdf"'

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
