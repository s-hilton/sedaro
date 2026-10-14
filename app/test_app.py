#!/usr/bin/env python3

"""
NOTE: Tests for the HTTP API, using an in-memory database. First build the `queries` binary with
`cargo build --release`, then run from `app/` with `python3 -m unittest test_app`.
"""

import io
import os
import unittest
import unittest.mock

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import numpy as np

from app import app
from modsim import rotation_matrix
from test_mesh import box, to_binary_stl


def body(x, vy, mass, **extra):
    return {"position": {"x": x, "y": 0, "z": 0}, "velocity": {"x": 0, "y": vy, "z": 0}, "mass": mass, **extra}


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        # A 40 x 10 x 10 bar with its origin at one corner; center of mass (20, 5, 5).
        response = self.client.post("/models", data={"file": (io.BytesIO(to_binary_stl(box((0, 0, 0), (40, 10, 10)))), "bar.stl")})
        self.assertEqual(response.status_code, 201)
        self.model = response.json

    def simulate(self, **model_fields):
        init = {"Body1": body(-0.73, -0.0015, 1), "Body2": body(60, 0.13, 0.12, **{"modelId": self.model["id"], **model_fields})}
        return self.client.post("/simulation", json=init)

    def test_upload_reports_mass_properties(self):
        self.assertEqual(self.model["dimensions"], {"x": 40, "y": 10, "z": 10})
        np.testing.assert_allclose([self.model["centerOfMass"][a] for a in "xyz"], [20, 5, 5])

    def test_mesh_is_served_relative_to_center_of_mass(self):
        response = self.client.get(f"/models/{self.model['id']}/mesh")
        self.assertEqual(response.status_code, 200)
        vertices = np.frombuffer(response.data, dtype="<f4").reshape(-1, 3)
        self.assertEqual(len(vertices), 3 * self.model["triangleCount"])
        np.testing.assert_allclose(vertices.min(axis=0), [-20, -5, -5])
        np.testing.assert_allclose(vertices.max(axis=0), [20, 5, 5])
        self.assertEqual(self.client.get("/models/9999/mesh").status_code, 404)

    def test_size_scales_model(self):
        start = self.simulate(size=4).json[0][2]["Body2"]
        self.assertEqual(start["model"]["dimensions"], {"x": 4, "y": 1, "z": 1})
        np.testing.assert_allclose([start["position"][a] for a in "xyz"], [62, 0.5, 0.5])
        self.assertAlmostEqual(start["inertia"]["yy"], 0.12 * (16 + 1) / 12)

    def test_orientation_rotates_body_and_center_of_mass_offset(self):
        start = self.simulate(size=4, orientation={"yaw": 90, "pitch": 0, "roll": 0}).json[0][2]["Body2"]
        # Yawed 90 degrees, the model's x axis points along +y, so its (2, 0.5, 0.5) offset becomes (-0.5, 2, 0.5).
        np.testing.assert_allclose([start["position"][a] for a in "xyz"], [59.5, 2, 0.5], atol=1e-12)
        np.testing.assert_allclose(rotation_matrix(start["attitude"]) @ [1, 0, 0], [0, 1, 0], atol=1e-12)
        self.assertEqual(start["model"]["orientation"], {"yaw": 90, "pitch": 0, "roll": 0})

    def test_orientation_defaults_to_simulation_axes(self):
        start = self.simulate(size=4).json[0][2]["Body2"]
        np.testing.assert_allclose([start["attitude"][a] for a in "wxyz"], [1, 0, 0, 0])

    def test_bodies_at_same_position_rejected(self):
        response = self.client.post("/simulation", json={"Body1": body(0, 0, 1), "Body2": body(0, 0.1, 1)})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["error"], "Body1 and Body2 start at the same position; move one of them.")

    def test_failed_simulation_reports_why(self):
        init = {"Body1": body(-0.73, -0.0015, 1), "Body2": body(60, 0.13, 0.12)}
        with unittest.mock.patch("app.Simulator.simulate", side_effect=RuntimeError("steps stopped advancing")):
            response = self.client.post("/simulation", json=init)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json["error"], "Simulation failed: steps stopped advancing")

    def test_invalid_inputs_rejected(self):
        self.assertEqual(self.simulate(size=-1).status_code, 400)
        self.assertEqual(self.simulate(orientation={"yaw": "north"}).status_code, 400)
        self.assertEqual(self.simulate(modelId=9999).status_code, 400)


if __name__ == "__main__":
    unittest.main()
