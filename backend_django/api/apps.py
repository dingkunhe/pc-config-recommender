from django.apps import AppConfig
import os

class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'

    def ready(self):
        # We only want to start the scheduler in the main process, not in migrations or reloader thread
        # runserver uses two threads, we avoid double starting by checking RUN_MAIN
        if os.environ.get('RUN_MAIN', None) == 'true':
            from .scheduler import start_scheduler
            start_scheduler()
