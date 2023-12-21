from django.contrib import admin
from app.models import *

# Register your models here.
admin.site.register(Employee)

admin.site.register(Parent)

admin.site.register(Provider)


@admin.register(Time)
class TimeAdmin(admin.ModelAdmin):
    list_display = ('engagement', 'employee', 'ts_date', 'hours', 'time_type_id', 'note')


@admin.register(Timecode)
class TimecodeAdmin(admin.ModelAdmin):
    list_display = ('time_code', 'time_code_desc', 'time_code_hours')


admin.site.register(EmployeeTitles)


@admin.register(Engagement)
class EngagementAdmin(admin.ModelAdmin):
    list_display = ('engagement_srg_id', 'time_code', 'parent', 'provider')


admin.site.register(Expense)


@admin.register(Todolist)
class TodolistAdmin(admin.ModelAdmin):
    list_display = ('engagement', 'employee', 'todo_date', 'todo_date_end', 'anticipated_hours', 'note')
    list_filter = ('employee',)


@admin.register(EngagementNotes)
class EngagementNotesAdmin(admin.ModelAdmin):
    list_display = ('engagement', 'employee', 'note_date', 'note')
    list_filter = ('employee',)
