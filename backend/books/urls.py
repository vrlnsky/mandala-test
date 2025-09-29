from django.urls import path
from .views import get_book_by_isbn, get_related_by_isbn


urlpatterns = [
    path('books/<str:isbn>/', get_book_by_isbn, name='get_book_by_isbn'),
    path('related/<str:isbn>/', get_related_by_isbn, name='get_related_by_isbn'),
]

