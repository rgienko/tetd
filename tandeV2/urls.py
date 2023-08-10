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
from django.urls import path
from app import views
import uuid

urlpatterns = [
    path('', views.login, name='login'),
    path('register/', views.register, name='register'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('timesheet/', views.EmployeeTimesheet, name='employee-timesheet'),
    path('todolist/', views.EmployeeTodolist, name='employee-todolist'),
    path('expenses/', views.EmployeeExpense, name='employee-expenses'),
    path('admin-dashboard/', views.AdminDashboard, name='admin-dashboard'),
    path('admin-dashboard/generatepdf/<mnth>/', views.createEmployeeHoursCompilationReport, name='generate-report-pdf'),
    path('engagement-dashboard/', views.EngagementDashboard, name='engagement-dashboard'),
    path('engagement-detail/<pk>/', views.AdminEngagementDetail, name='engagement-detail'),
    path('admin-timesheet/', views.AdminTimesheet, name='admin-timesheet'),
    path('admin-planning/', views.AdminPlanning, name='admin-planning'),
    path('assign/<pk>', views.AssignmentProjects, name='admin-assign'),
    path('extract-engagement-ts/<pk>', views.ExtractEngagementTimesheet, name='extract-engagement-entries'),
    path('update-engagement-status/<pk>', views.UpdateEngagementStatus, name='update-engagement-status'),
    path('renew-engagement/<pk>', views.RenewEngagement, name='renew-engagement'),
    path('add-engagement-assign/<int:eng>/<emp>/', views.AddAssignment, name='add-engagement-assign'),
    path('remove-engagement-assign/<int:eng>/<emp>/', views.RemoveAssignment, name='remove-engagement-assign'),
    path('admin/', admin.site.urls),
]
