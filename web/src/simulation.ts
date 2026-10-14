// Shapes of the data returned by `GET /simulation`.

export type Vector = { x: number; y: number; z: number };
export type Quaternion = { w: number; x: number; y: number; z: number };

export interface AgentData {
  time: number;
  position: Vector; // center of mass
  velocity: Vector;
  attitude?: Quaternion; // body to inertial; missing in runs saved before rigid bodies were added
  angularVelocity: Vector; // body frame
  // Present in the initial state of bodies simulated from an uploaded CAD model.
  model?: {
    id: number;
    filename: string;
    size: number;
    scale: number; // simulation units per model unit
    dimensions: Vector; // scaled bounding box
    orientation?: { yaw: number; pitch: number; roll: number }; // missing in runs saved before it was added
  };
}

export type DataFrame = Record<string, AgentData>;

// [start time, end time, states produced over that interval]. The first entry is the initial state
// of every agent.
export type DataPoint = [number, number, DataFrame];
