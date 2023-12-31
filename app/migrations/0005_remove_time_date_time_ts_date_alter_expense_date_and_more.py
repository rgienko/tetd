# Generated by Django 4.2.2 on 2023-09-07 02:17

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0004_todolist_todo_date_end_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='time',
            name='date',
        ),
        migrations.AddField(
            model_name='time',
            name='ts_date',
            field=models.DateField(default=datetime.date(2023, 9, 6)),
        ),
        migrations.AlterField(
            model_name='expense',
            name='date',
            field=models.DateField(default=datetime.date(2023, 9, 6)),
        ),
        migrations.AlterField(
            model_name='todolist',
            name='todo_date',
            field=models.DateField(default=datetime.date(2023, 9, 6)),
        ),
    ]
