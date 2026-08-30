from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0014_remove_registrationrequest_password_hash_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='registrationrequest',
            name='setup_token_hash',
            field=models.CharField(blank=True, db_index=True, editable=False, max_length=64),
        ),
    ]
