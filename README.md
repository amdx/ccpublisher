# ccpublisher - Cameo Collaborator publisher service

Headless publisher service for Magicdraw to
[Cameo Collaborator for Teamwork Cloud](https://www.3ds.com/products-services/catia/products/no-magic/cameo-collaborator-for-teamwork-cloud/).

Publishing a project from Magicdraw can take hours to complete, preventing any
further operation on its interface. CCpublisher allows to enqueue publishing
operations and to track their progress via a convenient web interface. 

## Running from this repo

In order to run it for a local test:

```shell
$ poetry install
$ poetry run ccpublisher examples/local_config.yaml
```

Open http://localhost:9999 to access the service's UI.

## Installation

Create a virtualenv and use pip to install the package:

```shell
$ python3 -m venv /opt/amdx/ccpublisher
$ source /opt/amdx/ccpublisher/bin/activate
$ pip install ccpublisher
```

Create the following folders:

```shell
$ cd /opt/amdx/ccpublisher
$ mkdir etc var
```

Copy the following files from the `examples` folder:

```shell
$ cp /path/to/examples/{config.yaml,template.properties} etc/
```

* Modify `template.properties` and add cflbot's password.
* Modify `config.yaml`, in particular:
  * Adjust `publisher.script`: this is the path to the publisher plugin launcher
  * Adjust `fileobserver.file_path`: this should point to magicdraw's logfile

Install the unit file for systemd:

```shell
$ sudo cp /path/to/examples/ccpublisher.service /etc/systemd/system/
$ sudo systemctl enable ccpublisher
$ sudo systemctl start ccpublisher
```

Logs entries can be found in the syslog or:

```shell
$ sudo journalctl -fu ccpublisher
```
