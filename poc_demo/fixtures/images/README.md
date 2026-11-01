# Image fixtures

`synthetic.png` is a deterministic 1×1 synthetic PNG used by automated tests.

The existing invoice images are read only from the server-configured `POC_IMAGES_DIR`.
Its host default is `/home/elmehdi/Desktop/invoices/test_invoices`; Docker mounts that directory read-only at `/app/source_invoices`.

No existing sample image is modified or deleted. Images acquired from that source are copied into checksum-based raw storage.
