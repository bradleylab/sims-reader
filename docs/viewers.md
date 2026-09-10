# Existing viewers and OME-Zarr

Use existing viewers for image exploration and ROI drawing. This repository remains a translator. The first acquisition has been loaded as four image layers in napari 0.9.1 on macOS. Interactive ROI workflows have not yet been tested.

## First choice: napari

[napari](https://napari.org/stable/) is an open-source desktop image viewer. Its [Shapes layer](https://napari.org/stable/howtos/layers/shapes.html) supports editable rectangles, polygons, ellipses, and other geometry. It fits local multichannel image exploration and pixel-coordinate ROI work. Scientific ROI calculations and geometry persistence should use a documented external workflow.

Plain Zarr does not imply automatic interpretation by every viewer plugin. In a separate environment containing napari and Zarr, this short loading example displays one acquisition without loading the entire acquisition series:

```python
import napari
import zarr

root = zarr.open_group("../results/CN_SiA_1.zarr", mode="r")
assert root["conversion"].attrs["conversion_status"] == "complete"
viewer = napari.Viewer()
viewer.add_image(
    root["stored_signal"][0, :, :, :],
    channel_axis=0,
    name=list(root["channel_label"][:]),
    axis_labels=("row", "column"),
)
napari.run()
```

This loading sequence was exercised with the installed napari 0.9.1; that version does not expose `napari.view_image`. No physical scale is assigned. The [napari-ome-zarr plugin](https://github.com/ome/napari-ome-zarr) is another route for OME-Zarr data; our current plain Zarr output does not claim that plugin's drag-and-drop compatibility.

[Vizarr](https://github.com/hms-dbmi/vizarr) is an open-source browser/notebook viewer worth evaluating for later sharing. Its generic Zarr support is less tested than its pyramidal OME-Zarr support. A complete ROI editing and persistence workflow has not been established here.

## Does OME-Zarr make sense?

Yes as a possible interoperability export. OME-Zarr adds standardized image axes, scales, channels, and multiscale metadata to Zarr so existing microscopy tools can interpret datasets consistently. [OME-NGFF 0.5](https://ngff.openmicroscopy.org/0.5/) uses Zarr v3; [0.4](https://ngff.openmicroscopy.org/0.4/) uses Zarr v2. Matching those versions matters for viewer support.

The current obstacle is acquisition semantics. Our array is acquisition-index × channel × row × column. The 0.5 multiscales axis rules permit spatial axes, an optional time axis, and one channel or custom axis. A separate custom acquisition axis alongside the channel axis does not directly fit those rules. Calling acquisition index elapsed time or depth would imply an interpretation we have not established.

Possible future exports are a collection of channel × y × x images, one per acquisition, or time × channel × y × x after confirming acquisition semantics. A derived projection would require a separately agreed method. Unknown physical calibration must remain explicit. For now, ordinary Zarr preserves the evidence without forcing a microscopy interpretation. OME-Zarr compatibility should be tested with the chosen existing viewer before it is promised.

## Local installation

Napari 0.9.1 with PyQt6 and Zarr 3.3.0 is installed in the surrounding workspace's `.venv-napari`, separate from the converter environment. Napari supports macOS, Windows, and Linux; see its [installation documentation](https://napari.org/stable/tutorials/fundamentals/installation).

Launch an empty viewer from the surrounding workspace directory:

```sh
.venv-napari/bin/napari
```

To use the Python loading example above, run it with `../.venv-napari/bin/python` from this repository directory. The relative store path in that example assumes this repository directory. This installation does not create a macOS Applications shortcut.
