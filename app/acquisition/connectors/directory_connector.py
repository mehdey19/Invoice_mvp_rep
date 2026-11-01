from app.acquisition.connectors.file_connector import read_file
from app.acquisition.settings import EXTENSIONS, allowed_path, images_dir


class DirectoryConnector:
    def acquire(self, source):
        config = source["config"]
        directory = images_dir() if config.get("env_dir") == "POC_IMAGES_DIR" else allowed_path(config["path"])
        if not directory.is_dir():
            raise ValueError("Configured source directory does not exist")
        allowed = EXTENSIONS[source["data_format"]]
        count = 0
        for file in sorted(directory.iterdir()):
            if file.is_symlink() or not file.is_file() or file.suffix.lower() not in allowed:
                continue
            count += 1
            if count > 1000:
                raise ValueError("Directory exceeds the 1000-file POC limit")
            yield read_file(allowed_path(str(file)))
        if not count:
            raise ValueError("No matching files in configured directory")
