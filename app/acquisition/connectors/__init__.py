from .file_connector import FileConnector
from .directory_connector import DirectoryConnector
from .http_connector import HTTPConnector

CONNECTORS = {"FILE": FileConnector, "DIRECTORY": DirectoryConnector, "HTTP_GET": HTTPConnector}
