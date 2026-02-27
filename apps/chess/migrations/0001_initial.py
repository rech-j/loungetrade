from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ChessGame',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('creator_side', models.CharField(choices=[('white', 'White'), ('black', 'Black'), ('random', 'Random')], default='random', max_length=6)),
                ('stake', models.PositiveIntegerField()),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('active', 'Active'), ('completed', 'Completed'), ('cancelled', 'Cancelled')], default='pending', max_length=10)),
                ('end_reason', models.CharField(blank=True, choices=[('checkmate', 'Checkmate'), ('stalemate', 'Stalemate'), ('draw', 'Draw agreed'), ('resign', 'Resignation'), ('timeout', 'Timeout'), ('cancelled', 'Cancelled')], max_length=10, null=True)),
                ('fen', models.CharField(default='rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1', max_length=200)),
                ('moves_uci', models.TextField(blank=True)),
                ('white_time', models.PositiveIntegerField(default=600)),
                ('black_time', models.PositiveIntegerField(default=600)),
                ('last_move_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('ended_at', models.DateTimeField(blank=True, null=True)),
                ('black_player', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='chess_as_black', to=settings.AUTH_USER_MODEL)),
                ('creator', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chess_created', to=settings.AUTH_USER_MODEL)),
                ('opponent', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chess_received', to=settings.AUTH_USER_MODEL)),
                ('white_player', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='chess_as_white', to=settings.AUTH_USER_MODEL)),
                ('winner', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='chess_wins', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at'], 'indexes': [models.Index(fields=['status', 'created_at'], name='apps_chess__status_5e0f0c_idx')]},
        ),
    ]
