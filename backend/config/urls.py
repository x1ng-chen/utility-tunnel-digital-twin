from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('operations.urls')),
]

handler404 = 'config.api.api_handler404'
handler500 = 'config.api.api_handler500'
