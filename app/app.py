# HTTP SERVER

import json

from flask import Flask, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from mesh import MeshError, mass_properties, parse_stl
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
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # largest accepted upload (a ~1M-triangle binary STL)
db.init_app(app)

logging.basicConfig(level=logging.INFO)

############################## Database Models ##############################


class Simulation(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[str]


class CadModel(db.Model):
    """Mass properties of an uploaded CAD model. The mesh itself is not kept."""
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str]
    triangle_count: Mapped[int]
    volume: Mapped[float]
    com_x: Mapped[float]
    com_y: Mapped[float]
    com_z: Mapped[float]

    def to_dict(self):
        return {
            "id": self.id,
            "filename": self.filename,
            "triangleCount": self.triangle_count,
            "volume": self.volume,
            "centerOfMass": {"x": self.com_x, "y": self.com_y, "z": self.com_z},
        }


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
        props = mass_properties(parse_stl(file.read()))
    except MeshError as e:
        return {"error": str(e)}, 400

    com = props["centerOfMass"]
    model = CadModel(
        filename=file.filename,
        triangle_count=props["triangleCount"],
        volume=props["volume"],
        com_x=com["x"],
        com_y=com["y"],
        com_z=com["z"],
    )
    db.session.add(model)
    db.session.commit()
    return model.to_dict(), 201


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
    #     "Body2": {..., "modelId": 3},
    # }
    # A body with a `modelId` is the uploaded CAD model with its origin at `position`. The model is
    # treated as a uniform-density solid of the given mass, so it is simulated at its center of mass.

    # Define time and timeStep for each agent
    init: dict = request.json
    for key in init.keys():
        init[key]["time"] = 0
        init[key]["timeStep"] = 0.01
        model_id = init[key].pop("modelId", None)
        if model_id is not None:
            model = db.session.get(CadModel, model_id)
            if model is None:
                return {"error": f"Unknown modelId {model_id} for {key}."}, 400
            com = model.to_dict()["centerOfMass"]
            init[key]["position"] = {axis: init[key]["position"][axis] + com[axis] for axis in "xyz"}
            init[key]["model"] = model.to_dict()

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
