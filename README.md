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

## Documentation

Documentation can be found here: https://amdx.github.io/ccpublisher/
