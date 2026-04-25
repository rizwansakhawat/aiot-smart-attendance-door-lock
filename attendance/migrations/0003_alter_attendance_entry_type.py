from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0002_notificationstate'),
    ]

    operations = [
        migrations.AlterField(
            model_name='attendance',
            name='entry_type',
            field=models.CharField(
                choices=[('success', 'Access Granted')],
                default='success',
                max_length=20,
                verbose_name='Entry Type',
            ),
        ),
    ]
