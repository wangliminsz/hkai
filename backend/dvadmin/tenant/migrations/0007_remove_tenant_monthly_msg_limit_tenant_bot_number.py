# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenant', '0006_alter_tenant_bot_number'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='tenant',
            name='monthly_msg_limit',
        ),
        migrations.RemoveField(
            model_name='tenant',
            name='bot_number',
        ),
    ]
