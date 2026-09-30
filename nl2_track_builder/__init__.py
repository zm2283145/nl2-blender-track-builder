bl_info = {
    "name": "NL2 Track Builder",
    "author": "NL2 reverse-engineering project",
    "version": (1, 2, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > NL2",
    "description": "Sweep NoLimits 2 track styles along an exported centre-of-rails spline and build supports "
                   "from an NL2 supports XML",
    "category": "Import-Export",
}


def register():
    from . import ui
    ui.register()


def unregister():
    from . import ui
    ui.unregister()
