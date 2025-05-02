import django_filters
from django_filters.widgets import RangeWidget
from django.utils.translation import gettext_lazy as _
from rest_framework import request

from app.models import *
from django import forms
from django import template
from app.widget import DatePickerInput

register = template.Library()

@register.filter
def tuple_lookup(dictionary, key):
    return dictionary.get(key, "-")

class EngagementFilter(django_filters.FilterSet):
    fye = django_filters.DateFilter(field_name='fye', lookup_expr='exact', label='Fiscal Year',
                                    widget=DatePickerInput())

    class Meta:
        model = Engagement
        fields = {
            'time_code': ['exact'],
            'parent': ['exact']
        }


class TimesheetFilter(django_filters.FilterSet):
    start_date = django_filters.DateFilter(field_name='ts_date', label='Start Date:', lookup_expr='gte',
                                           widget=DatePickerInput)
    end_date = django_filters.DateFilter(field_name='ts_date', label='End Date:', lookup_expr='lte',
                                         widget=DatePickerInput)

    class Meta:
        model = Time
        fields = {
            'employee': ['exact'],
            'engagement__time_code': ['exact'],
            'engagement__parent': ['exact'],
            'engagement__fye': ['exact']
        }

        widgets = {
            'engagement__time_code': django_filters.ModelChoiceFilter(widget=forms.Select(attrs={
                'style': 'white-space: normal; width:75%'}))
        }


class TimesheetFilterPrevious(django_filters.FilterSet):
    # employee = django_filters.CharFilter(field_name='employee')
    # engagement__provider = django_filters.CharFilter(field_name='engagement', lookup_expr='icontains')
    # period = django_filters.DateFromToRangeFilter(field_name='ts_date', label='Period:')
    start_date = django_filters.DateFilter(field_name='ts_date', label='Start Date:', lookup_expr='gte',
                                           widget=DatePickerInput, required=False)
    end_date = django_filters.DateFilter(field_name='ts_date', label='End Date:', lookup_expr='lte',
                                         widget=DatePickerInput, required=False)

    class Meta:
        model = Time
        fields = {
            'engagement__time_code': ['exact'],
            'engagement__parent': ['exact']

        }


class ExpenseFilter(django_filters.FilterSet):
    # employee = django_filters.CharFilter(field_name='employee')
    # engagement__provider = django_filters.CharFilter(field_name='engagement', lookup_expr='icontains')
    start_date = django_filters.DateFilter(field_name='date', label='Start Date:', lookup_expr='gte',
                                           widget=DatePickerInput, required=False)
    end_date = django_filters.DateFilter(field_name='date', label='End Date:', lookup_expr='lte',
                                         widget=DatePickerInput, required=False)

    class Meta:
        model = Expense
        fields = []


class AdminTodoListFilter(django_filters.FilterSet):
    class Meta:
        model = Todolist
        fields = ['employee']

