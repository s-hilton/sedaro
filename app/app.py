# HTTP SERVER

import copy
import json
import math
import os

from flask import Flask, Response, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from mesh import MeshError, inertia_from_dict, inertia_to_dict, mass_properties, parse_stl
from modsim import POINT_MASS, attitude_from_euler, rotation_matrix
import numpy as np
from simulator import Simulator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from store import QRangeStore
import logging
from datetime import datetime

class Base(DeclarativeBase):
    pass


############################## Application Configuration ##############################

app = Flask(__name__)
CORS(app, origins=["http://localhost:3030"])

db = SQLAlchemy(model_class=Base)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///database.db")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # largest accepted upload (a ~1M-triangle binary STL)
db.init_app(app)

logging.basicConfig(level=logging.INFO)

############################## Database Models ##############################


class Simulation(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[str]


class CadModel(db.Model):
    """
    Mass properties of an uploaded CAD model, in the STL file's own (unitless) coordinates, as
    computed by `mesh.mass_properties`. The mesh itself is not kept.
    """
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str]
    properties: Mapped[str]  # JSON

    def to_dict(self):
        return {"id": self.id, "filename": self.filename, **json.loads(self.properties)}


class CadMesh(db.Model):
    """
    Triangles of an uploaded CAD model for display, as little-endian float32 (x, y, z) vertices,
    three per triangle, in the STL's units with the origin moved to the center of mass. Kept apart
    from `CadModel` so listing or simulating models never loads the mesh.
    """
    model_id: Mapped[int] = mapped_column(db.ForeignKey(CadModel.id), primary_key=True)
    vertices: Mapped[bytes]


with app.app_context():
    db.create_all()


############################## API Endpoints ##############################


@app.get("/")
def health():
    return "<p>Sedaro Nano API - running!</p>"


@app.errorhandler(413)
def upload_too_large(e):
    return {"error": f"File is larger than the {app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)} MB upload limit."}, 413


@app.post("/models")
def upload_model():
    # Accepts a multipart upload with an STL file in the `file` field and returns its volume and
    # center of mass (assuming uniform density), in the model's own coordinates and units.
    file = request.files.get("file")
    if file is None or not file.filename:
        return {"error": "Upload an STL file in the 'file' field."}, 400
    try:
        triangles = parse_stl(file.read())
        props = mass_properties(triangles)
    except MeshError as e:
        return {"error": str(e)}, 400

    model = CadModel(filename=file.filename, properties=json.dumps(props))
    db.session.add(model)
    db.session.flush()  # assigns model.id
    com = np.array([props["centerOfMass"][axis] for axis in "xyz"])
    db.session.add(CadMesh(model_id=model.id, vertices=(triangles - com).astype("<f4").tobytes()))
    db.session.commit()
    return model.to_dict(), 201


@app.get("/models/<int:model_id>/mesh")
def get_model_mesh(model_id):
    # The model's triangles for display: float32 (x, y, z) vertices, three per triangle, in the
    # model's own units, relative to its center of mass.
    mesh = db.session.get(CadMesh, model_id)
    if mesh is None:
        return {"error": f"No mesh stored for model {model_id}."}, 404
    return Response(mesh.vertices, mimetype="application/octet-stream")


def place_model(body: dict, model: CadModel, size: float, orientation: dict):
    """
    Make `body` the rigid body described by `model`, scaled uniformly so that its longest dimension
    is `size` simulation length units, with uniform density, its origin at the body's `position`,
    and rotated from the simulation axes by `orientation` (yaw, pitch, roll in degrees).
    """
    props = model.to_dict()
    scale = size / max(props["dimensions"].values())
    body["attitude"] = attitude_from_euler(orientation["yaw"], orientation["pitch"], orientation["roll"])
    # The body is simulated at its center of mass, which scales and rotates with the model.
    com = rotation_matrix(body["attitude"]) @ np.array([props["centerOfMass"][axis] for axis in "xyz"])
    body["position"] = {axis: body["position"][axis] + scale * float(c) for axis, c in zip("xyz", com)}
    # Inertia about the center of mass: mass times the per-unit-mass inertia, which scales with size^2.
    inertia = body["mass"] * scale**2 * inertia_from_dict(props["inertiaPerUnitMass"])
    body["inertia"] = inertia_to_dict(inertia)
    body["model"] = {
        "id": props["id"],
        "filename": props["filename"],
        "size": size,
        "scale": scale,
        "orientation": orientation,
        "dimensions": {axis: scale * v for axis, v in props["dimensions"].items()},
        "volume": scale**3 * props["volume"],
    }


@app.get("/simulation")
def get_data():
    # Get most recent simulation from database
    simulation: Simulation = Simulation.query.order_by(Simulation.id.desc()).first()
    return simulation.data if simulation else []


@app.post("/simulation")
def simulate():
    # Get data from request in this form
    # init = {
    #     "Body1": {"position": {"x": 0, "y": 0, "z": 0}, "velocity": {"x": 0, "y": 0, "z": 0}, "mass": 1},
    #     "Body2": {..., "modelId": 3, "size": 2.5, "angularVelocity": {"x": 0, "y": 0, "z": 0.01},
    #               "orientation": {"yaw": 30, "pitch": 0, "roll": 0}},
    # }
    # A body with a `modelId` is the uploaded CAD model, scaled so its longest dimension is `size`,
    # with its origin at `position`, turned from the simulation axes by `orientation` (Z-Y-X Euler
    # angles in degrees). It is a uniform-density rigid body of the given mass, starting with
    # body-frame `angularVelocity`. Other bodies are point masses.

    # Define time and timeStep for each agent
    init: dict = request.json
    for key, body in init.items():
        model_id = body.pop("modelId", None)
        size = body.pop("size", None)
        spin = body.pop("angularVelocity", None)
        orientation = body.pop("orientation", None) or {}
        body.update(copy.deepcopy(POINT_MASS), time=0, timeStep=0.01)
        if model_id is None:
            continue
        model = db.session.get(CadModel, model_id)
        if model is None:
            return {"error": f"Unknown modelId {model_id} for {key}."}, 400
        if size is None:
            size = max(model.to_dict()["dimensions"].values())
        if not isinstance(size, (int, float)) or not math.isfinite(size) or size <= 0:
            return {"error": f"{key}'s size must be a positive number."}, 400
        if spin is not None:
            body["angularVelocity"] = {axis: spin[axis] for axis in "xyz"}
        orientation = {angle: orientation.get(angle, 0) for angle in ("yaw", "pitch", "roll")}
        if not all(isinstance(a, (int, float)) and math.isfinite(a) for a in orientation.values()):
            return {"error": f"{key}'s orientation angles must be numbers."}, 400
        place_model(body, model, size, orientation)

    # Create store and simulator
    t = datetime.now()
    store = QRangeStore()
    simulator = Simulator(store=store, init=init)
    logging.info(f"Time to Build: {datetime.now() - t}")

    # Run simulation
    t = datetime.now()
    simulator.simulate()
    logging.info(f"Time to Simulate: {datetime.now() - t}")

    # Save data to database
    simulation = Simulation(data=json.dumps(store.store))
    db.session.add(simulation)
    db.session.commit()

    return store.store
