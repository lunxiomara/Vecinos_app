from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('incidencias', '0005_m5_outbox_events'),
    ]

    _renames_and_alters = [
        migrations.RenameField(
            model_name='edificio',
            old_name='id',
            new_name='id_edif',
        ),
        migrations.AlterField(
            model_name='edificio',
            name='id_edif',
            field=models.AutoField(primary_key=True, serialize=False),
        ),
        migrations.RenameField(
            model_name='incidencia',
            old_name='id',
            new_name='id_incid',
        ),
        migrations.AlterField(
            model_name='incidencia',
            name='id_incid',
            field=models.AutoField(primary_key=True, serialize=False),
        ),
        migrations.RenameField(
            model_name='perfil',
            old_name='id',
            new_name='id_prfl',
        ),
        migrations.AlterField(
            model_name='perfil',
            name='id_prfl',
            field=models.AutoField(primary_key=True, serialize=False),
        ),
        migrations.RenameField(
            model_name='eventoincidencia',
            old_name='id',
            new_name='id_evinc',
        ),
        migrations.AlterField(
            model_name='eventoincidencia',
            name='id_evinc',
            field=models.AutoField(primary_key=True, serialize=False),
        ),
        migrations.RenameField(
            model_name='unidad',
            old_name='id',
            new_name='id_unit',
        ),
        migrations.AlterField(
            model_name='unidad',
            name='id_unit',
            field=models.AutoField(primary_key=True, serialize=False),
        ),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=_renames_and_alters,
            state_operations=_renames_and_alters,
        ),
    ]