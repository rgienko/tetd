"""
URL configuration for tandeV2 project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from app import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', views.login, name='login'),
    path('logout', views.logout_view, name='logout'),
    path('register/', views.register, name='register'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('timesheet/current/', views.EmployeeTimesheet, name='employee-timesheet'),
    path('timesheet/previous/', views.EmployeeTimesheetPrevious, name='employee-timesheet-previous'),
    path('timesheet/review/', views.EmployeeTimesheetReview, name='employee-timesheet-review'),
    path('todolist/', views.EmployeeTodolist, name='employee-todolist'),
    path('expenses/', views.EmployeeExpense, name='employee-expenses'),
    path('admin-dashboard/', views.AdminDashboard, name='admin-dashboard'),
    path('admin-dashboard/generatepdf/<mnth>/', views.createEmployeeHoursCompilationReport, name='generate-report-pdf'),
    path('engagement-dashboard/', views.EngagementDashboard, name='engagement-dashboard'),
    path('engagement-detail/<pk>/', views.AdminEngagementDetail, name='engagement-detail'),
    path('admin-timesheet/', views.AdminTimesheet, name='admin-timesheet'),
    path('admin-planning/', views.AdminPlanning, name='admin-planning'),
    path('admin-employee-dashboard/<pk>/<per_beg>/<per_end>/', views.AdminEmployeeDashboard, name='admin-employee-dashboard'),
    path('assign/<pk>', views.AssignmentProjects, name='admin-assign'),
    path('extract-engagement-ts/<pk>', views.ExtractEngagementTimesheet, name='extract-engagement-entries'),
    path('update-engagement-status/<pk>', views.UpdateEngagementStatus, name='update-engagement-status'),
    path('toggle-engagement-alerts/<pk>', views.ToggleEngagementAlerts, name='toggle-engagement-alerts'),
    path('renew-engagement/<pk>', views.RenewEngagement, name='renew-engagement'),
    path('add-engagement-assign/<int:eng>/<emp>/', views.AddAssignment, name='add-engagement-assign'),
    path('remove-engagement-assign/<int:eng>/<emp>/', views.RemoveAssignment, name='remove-engagement-assign'),
    path('delete-engagement-note/<int:pk>/', views.DeleteEngagementNote, name='delete-engagement-note'),
    path('delete-time-entry/<pk>/', views.DeleteTimesheetEntry, name='delete-time-entry'),
    path('get_ts/<int:ts_id>/', views.GetTsEntry, name='get-task'),
    path('update_cur_entry', views.UpdateTsEntry, name='update-ts'),
    path('update_prev_entry', views.UpdateRevTsEntry, name='update-rev-ts'),
    path('delete-todo-entry/<pk>/', views.DeleteTdEntry, name='delete-todo-entry'),
    path('get_td_list/<dte>/', views.GetTdDayList, name='get-td-list'),
    path('get_td_week_list/<week_beg>/<week_end>/', views.GetTdWeekList, name='get-td-week-list'),
    path('get_td/<int:td_id>/', views.GetTdEntry, name='get-td'),
    path('update_td/', views.UpdateTdEntry, name='update-td'),
    path('get_expense/<expense_id>/', views.GetExpenseEntry, name='get-expense'),
    path('update_expense/', views.UpdateExpenseEntry, name='update-expense'),
    path('update_expense_review/', views.RevUpdateExpenseEntry, name='update-expense-review'),
    path('delete-expense/<pk>/', views.DeleteExpenseEntry, name='delete-expense-entry'),
    path('delete-expense-review/<pk>/', views.RevDeleteExpenseEntry, name='rev-delete-expense-entry'),
    path('get_expense_list/<dte>/', views.GetExpenseDayList, name='get-expense-day-list'),
    path('admin/', admin.site.urls),
    path('forgot_password/', views.ForgotPassword, name='forgot-password'),
    path('forogt_password_dne/<pk>/', views.ForgotPassDone, name='forgot-password-done'),
    path('forgot_password_cfm/<str:uidb64>/<str:token>/', views.ForgotPassConfirm, name='forgot-password-confirm'),
    path('__debug__/', include('debug_toolbar.urls'))
]

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
