from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('operations', '0022_align_network_asset_with_esp8266')]

    # Operational/demo master data is created explicitly by `seed_demo`. Keeping
    # this migration data-free preserves isolation for clean and test databases.
    operations = []
