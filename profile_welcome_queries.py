import os
import django
from django.db import connection

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ngo.settings")
django.setup()

from django.test import RequestFactory
from django.contrib.auth.models import User
from heart_charity.views import welcome_view

rf = RequestFactory()
request = rf.get('/welcome/')
# Set a user
user = User.objects.filter(is_superuser=True).first()
if not user:
    user = User.objects.create_user(username="temp_admin", password="password")
request.user = user

# Enable query logging
from django.test.utils import CaptureQueriesContext

print("Profiling welcome_view...")
with CaptureQueriesContext(connection) as queries:
    response = welcome_view(request)
    
print(f"Total queries executed: {len(queries)}")
for idx, q in enumerate(queries.captured_queries):
    print(f"\nQuery #{idx+1} (Time: {q['time']}):")
    print(q['sql'])
