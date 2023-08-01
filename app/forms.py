from django import forms

from .models import *
from .widget import *
from django.utils.translation import gettext_lazy as _


class CreateEngagementForm(forms.ModelForm):
    class Meta:
        model = Engagement

        fields = ['provider', 'parent', 'start_date', 'time_code', 'fye', 'type']

        widgets = {
            'fye': DatePickerInput,
            'start_date': DatePickerInput
        }


class TimeForm(forms.ModelForm):
    class Meta:
        model = Time

        fields = ['date', 'hours', 'time_type_id', 'note']

        labels = {
            'date': _('Date'),
            'hours': _('Hours'),
            'time_type_id': _('Type'),
            'note': _('Note')
        }

        widgets = {
            'note': forms.Textarea(attrs={'rows': 5, 'cols': 40}),
            'date': DatePickerInput
        }


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense

        fields = ['expense_category', 'expense_amount']

        labels = {
            'engagement': _('Engagement'),
            'expense_category': _('Category'),
            'expense_amount': _('Amount')
        }


class TodoForm(forms.ModelForm):
    class Meta:
        model = Todolist

        fields = ['todo_date', 'anticipated_hours', 'note']

        labels = {
            'todo_date': _('Date'),
            'anticipated_hours': _('Expected Hours'),
            'note': _('Note')
        }

        widgets = {
            'note': forms.Textarea(attrs={'rows': 5, 'cols': 40}),
            'todo_date': DatePickerInput
        }


class UpdateEngagementStatusForm(forms.ModelForm):
    class Meta:
        model = Engagement

        fields = ['is_complete']