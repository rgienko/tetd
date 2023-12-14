import calendar

from django import forms
from django.contrib.auth.forms import SetPasswordForm

from .models import *
from .widget import *
from django.utils.translation import gettext_lazy as _


class CreateEngagementForm(forms.ModelForm):
    class Meta:
        model = Engagement

        fields = ['provider', 'parent', 'start_date', 'time_code', 'fye', 'type', 'is_rac',
                  'engagement_hourly_rate', 'budget_amount']

        widgets = {
            'fye': DatePickerInput,
            'start_date': DatePickerInput,
            'is_rac': forms.CheckboxInput(attrs={'size': 12}),
            'engagement_hourly_rate': forms.NumberInput(attrs={'width': 5})
        }


class TimeForm(forms.ModelForm):
    class Meta:
        model = Time

        fields = ['ts_date', 'hours', 'time_type_id', 'note']

        labels = {
            'ts_date': _('Date'),
            'hours': _('Hours'),
            'time_type_id': _('Type'),
            'note': _('Note')
        }

        widgets = {
            'note': forms.Textarea(attrs={'rows': 5, 'cols': 40}),
            'ts_date': DatePickerInput,
            'hours': forms.NumberInput(attrs={
                'step': '.25'
            })
        }


class EditTimeForm(forms.ModelForm):
    class Meta:
        model = Time

        fields = ['timesheet_id', 'engagement', 'ts_date', 'hours', 'time_type_id', 'note']

        labels = {
            'timesheet_id': _('Record #'),
            'engagement': _('Engagement'),
            'ts_date': _('Date'),
            'hours': _('Hours'),
            'time_type_id': _('Type'),
            'note': _('Note')
        }

        widgets = {
            'note': forms.Textarea(attrs={'rows': 5, 'cols': 40}),
            'ts_date': DatePickerInput
        }


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense

        fields = ['date', 'expense_category', 'expense_amount', 'time_type_id', 'expense_note']

        labels = {
            'engagement': _('Engagement'),
            'date': _('Date'),
            'expense_category': _('Category'),
            'expense_amount': _('Amount'),
            'time_type_id': _('Type'),
            'expense_note': _('Note')
        }

        widgets = {
            'date': DatePickerInput,
            'expense_note': forms.Textarea(attrs={'rows': 5, 'cols': 40})
        }


class TodoForm(forms.ModelForm):
    class Meta:
        model = Todolist

        fields = ['todo_date', 'todo_date_end', 'anticipated_hours', 'note']

        labels = {
            'todo_date': _('Start Date'),
            'todo_date_end': _('End Date'),
            'anticipated_hours': _('Hours per Day'),
            'note': _('Note')
        }

        widgets = {
            'note': forms.Textarea(attrs={'rows': 5, 'cols': 40}),
            'todo_date': DatePickerInput,
            'todo_date_end': DatePickerInput,
        }


class EditTodoForm(forms.ModelForm):
    class Meta:
        model = Todolist

        fields = ['engagement', 'todo_date', 'todo_date_end', 'anticipated_hours', 'note']

        labels = {
            'engagement': _('Engagement'),
            'todo_date': _('Start Date'),
            'todo_date_end': _('End Date'),
            'anticipated_hours': _('Hours per Day'),
            'note': _('Note')
        }

        widgets = {
            'note': forms.Textarea(attrs={'rows': 5, 'cols': 40}),
            'todo_date': DatePickerInput,
            'todo_date_end': DatePickerInput,
        }


class UpdateEngagementStatusForm(forms.ModelForm):
    class Meta:
        model = Engagement

        fields = ['is_complete']


class UserPasswordResetForm(SetPasswordForm):
    """Change password form."""
    new_password1 = forms.CharField(label='Password',
                                    help_text="<ul class='errorlist text-muted'><li>Your password can 't be too "
                                              "similar to your other personal"
                                              "information.</li><li>Your password must contain at least 8 characters.</li><li>Your password can "
                                              "'t be a commonly used password.</li> <li>Your password can 't be entirely numeric.<li></ul>",
                                    max_length=100,
                                    required=True,
                                    widget=forms.PasswordInput(
                                        attrs={
                                            'class': 'form-control',
                                            'placeholder': 'password',
                                            'type': 'password',
                                            'id': 'user_password',
                                        }))

    new_password2 = forms.CharField(label='Confirm password',
                                    help_text=False,
                                    max_length=100,
                                    required=True,
                                    widget=forms.PasswordInput(
                                        attrs={
                                            'class': 'form-control',
                                            'placeholder': 'confirm password',
                                            'type': 'password',
                                            'id': 'user_password',
                                        }))


class MonthSelectForm(forms.Form):
    MONTH_CHOICES = [(str(i), calendar.month_name[i]) for i in range(1, 13)]
    MONTH_CHOICES.append(('YTD', 'YTD'))

    month = forms.ChoiceField(choices=MONTH_CHOICES,
                              widget=forms.Select(attrs={'class': 'form-select', 'onchange': 'submit()'}))
