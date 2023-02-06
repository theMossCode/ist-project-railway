# Generated by Django 4.1.6 on 2023-02-05 21:01

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0002_alter_project_created_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='dataobject',
            name='widget_type',
            field=models.CharField(choices=[('SCATTER', 'Scatter Plot'), ('LINE', 'Line plot'), ('STATUS', 'Status Indicator'), ('MAP', 'Map')], default='LINE', max_length=10),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='project',
            name='created_date',
            field=models.DateTimeField(default=datetime.datetime(2023, 2, 6, 0, 1, 5, 203096)),
        ),
    ]