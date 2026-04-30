from rest_framework.pagination import PageNumberPagination


class CustomPagination(PageNumberPagination):
    """Custom pagination that allows page_size parameter from query string."""
    page_size_query_param = 'page_size'
    max_page_size = 1000
