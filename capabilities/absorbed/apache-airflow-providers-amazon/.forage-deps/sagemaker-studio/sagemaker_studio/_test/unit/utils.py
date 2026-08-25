from unittest.mock import Mock


def _create_mock_paginator(pages):
    class MockPageIterator:
        def __init__(self, pages):
            self.pages = pages

        def __iter__(self):
            return iter(self.pages)

    mock_paginator = Mock()
    mock_paginator.paginate.return_value = MockPageIterator(pages)
    return mock_paginator
