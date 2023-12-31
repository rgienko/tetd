# Generated by Django 4.2.2 on 2023-12-11 18:41

import datetime
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0007_expense_expense_note_alter_expense_date_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='expense',
            name='time_type_id',
            field=models.ForeignKey(default='B', on_delete=django.db.models.deletion.CASCADE, to='app.timetype'),
        ),
        migrations.AlterField(
            model_name='expense',
            name='date',
            field=models.DateField(default=datetime.date(2023, 12, 11)),
        ),
        migrations.AlterField(
            model_name='time',
            name='ts_date',
            field=models.DateField(default=datetime.date(2023, 12, 11)),
        ),
        migrations.AlterField(
            model_name='todolist',
            name='todo_date',
            field=models.DateField(default=datetime.date(2023, 12, 11)),
        ),
        migrations.AlterField(
            model_name='todolist',
            name='todo_date_end',
            field=models.DateField(blank=True, default=datetime.date(2023, 12, 11), null=True),
        ),
    ]
