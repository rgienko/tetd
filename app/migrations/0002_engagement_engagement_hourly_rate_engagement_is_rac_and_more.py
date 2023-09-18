# Generated by Django 4.2.2 on 2023-08-15 21:07

import datetime
import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='engagement',
            name='engagement_hourly_rate',
            field=models.IntegerField(blank=True, default=0, null=True, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(1000)]),
        ),
        migrations.AddField(
            model_name='engagement',
            name='is_rac',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='expense',
            name='date',
            field=models.DateField(default=datetime.date(2023, 8, 15)),
        ),
        migrations.AlterField(
            model_name='time',
            name='date',
            field=models.DateField(default=datetime.date(2023, 8, 15)),
        ),
        migrations.AlterField(
            model_name='todolist',
            name='todo_date',
            field=models.DateField(default=datetime.date(2023, 8, 15)),
        ),
    ]