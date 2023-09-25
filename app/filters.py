import django_filters
from django_filters.widgets import RangeWidget
from django.utils.translation import gettext_lazy as _

from app.models import *


class TimesheetFilter(django_filters.FilterSet):
    # employee = django_filters.CharFilter(field_name='employee')
    # engagement__provider = django_filters.CharFilter(field_name='engagement', lookup_expr='icontains')
    # period = django_filters.DateFromToRangeFilter(field_name='ts_date', label='Period:')
    start_date = django_filters.DateFilter(field_name='ts_date', label='Start Date:', lookup_expr='gte')
    end_date = django_filters.DateFilter(field_name='ts_date', label='End Date:', lookup_expr='lte')

    class Meta:
        model = Time
        fields = {
            'employee': ['exact'],
        }


class ExpenseFilter(django_filters.FilterSet):
    # employee = django_filters.CharFilter(field_name='employee')
    # engagement__provider = django_filters.CharFilter(field_name='engagement', lookup_expr='icontains')
    period = django_filters.DateFromToRangeFilter(field_name='date')

    class Meta:
        model = Expense
        fields = ['employee']


class AdminTodoListFilter(django_filters.FilterSet):
    class Meta:
        model = Todolist
        fields = ['employee']
