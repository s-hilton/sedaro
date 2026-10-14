import { Flex, Heading, Separator, Table } from '@radix-ui/themes';
import { useEffect, useState } from 'react';
import Plot from 'react-plotly.js';
import { Link } from 'react-router-dom';
import { Routes } from 'routes';

// Input data from the simulation
type Vector = { x: number; y: number; z: number };
interface AgentData {
  time: number;
  position: Vector;
  velocity: Vector;
  angularVelocity: Vector;
  // Present in the initial state of bodies simulated from an uploaded CAD model.
  model?: { filename: string; size: number; dimensions: Vector };
}
type DataFrame = Record<string, AgentData>;
type DataPoint = [number, number, DataFrame];

// Output data to the plot
type PlottedAgentData = Record<string, number[]>;
type PlottedFrame = Record<string, PlottedAgentData>;
type PlottedSeries = { name: string; x: number[]; y: number[]; type: 'scatter'; mode: 'lines' };

const App = () => {
  // Store plot data in state.
  const [positionData, setPositionData] = useState<PlottedAgentData[]>([]);
  const [velocityData, setVelocityData] = useState<PlottedAgentData[]>([]);
  const [angularVelocityData, setAngularVelocityData] = useState<PlottedSeries[]>([]);
  const [initialState, setInitialState] = useState<DataFrame>({});

  useEffect(() => {
    // fetch plot data when the component mounts
    let canceled = false;

    async function fetchData() {
      console.log('calling fetchdata...');

      try {
        // data should be populated from a POST call to the simulation server
        const response = await fetch('http://localhost:8000/simulation');
        if (canceled) return;
        const data: DataPoint[] = await response.json();
        const updatedPositionData: PlottedFrame = {};
        const updatedVelocityData: PlottedFrame = {};

        // NOTE: Uncomment to see the raw data in the console
        // console.log('Data:', data);

        setInitialState(data[0][2]);

        const baseData = (name: string) => ({
          name,
          x: [],
          y: [],
          z: [],
          type: 'scatter3d',
          mode: 'lines+markers',
          marker: { size: 4 },
          line: { width: 2 },
        });

        data.forEach(([t0, t1, frame]) => {
          for (let [agentId, val] of Object.entries(frame)) {
              if (agentId == "time" || agentId == "timeStep") {
                continue;
              }
              let {position, velocity} = val;
              updatedPositionData[agentId] = updatedPositionData[agentId] || baseData(agentId);
              updatedPositionData[agentId].x.push(position.x);
              updatedPositionData[agentId].y.push(position.y);
              updatedPositionData[agentId].z.push(position.z);

              updatedVelocityData[agentId] = updatedVelocityData[agentId] || baseData(agentId);
              updatedVelocityData[agentId].x.push(velocity.x);
              updatedVelocityData[agentId].y.push(velocity.y);
              updatedVelocityData[agentId].z.push(velocity.z);
          }
        });
        setPositionData(Object.values(updatedPositionData));
        setVelocityData(Object.values(updatedVelocityData));

        // Rotation over time for bodies simulated as rigid bodies (those with a CAD model).
        const rigidBodies = Object.keys(data[0][2]).filter((agentId) => data[0][2][agentId].model);
        const updatedAngularVelocityData: PlottedSeries[] = rigidBodies.flatMap((agentId) =>
          (['x', 'y', 'z'] as const).map((axis) => {
            const states = [data[0][2][agentId], ...data.slice(1).flatMap(([, , frame]) => (frame[agentId] ? [frame[agentId]] : []))];
            return {
              name: `${agentId} ω${axis}`,
              x: states.map((state) => state.time),
              y: states.map((state) => state.angularVelocity[axis]),
              type: 'scatter',
              mode: 'lines',
            };
          })
        );
        setAngularVelocityData(updatedAngularVelocityData);
        console.log('Set plot data!');
      } catch (error) {
        console.error('Error fetching data:', error);
      }
    }

    fetchData();

    return () => {
      canceled = true;
    };
  }, []);

  return (
    <div
      style={{
        height: '100vh',
        width: '100vw',
        margin: '0 auto',
      }}
    >
      {/* Flex: https://www.radix-ui.com/themes/docs/components/flex */}
      <Flex direction="column" m="4" width="100%" justify="center" align="center">
        <Heading as="h1" size="8" weight="bold" mb="4">
          Simulation Data
        </Heading>
        <Link to={Routes.FORM}>Define new simulation parameters</Link>
        <Separator size="4" my="5" />
        <Flex direction="row" width="100%" justify="center">
          <Plot
            style={{ width: '45%', height: '100%', margin: '5px' }}
            data={positionData}
            layout={{
              title: 'Position',
              scene: {
                xaxis: { title: 'X' },
                yaxis: { title: 'Y' },
                zaxis: { title: 'Z' },
                // Fixed proportions, so a nearly flat orbit with a little out-of-plane motion isn't
                // stretched into a line by z being scaled up to match x and y.
                aspectmode: 'manual',
                aspectratio: { x: 1, y: 1, z: 0.4 },
              },
              autosize: true,
              dragmode: 'turntable',
            }}
            useResizeHandler
            config={{
              scrollZoom: true,
            }}
          />
          <Plot
            style={{ width: '45%', height: '100%', margin: '5px' }}
            data={velocityData}
            layout={{
              title: 'Velocity',
              scene: {
                xaxis: { title: 'X' },
                yaxis: { title: 'Y' },
                zaxis: { title: 'Z' },
                // Fixed proportions, so a nearly flat orbit with a little out-of-plane motion isn't
                // stretched into a line by z being scaled up to match x and y.
                aspectmode: 'manual',
                aspectratio: { x: 1, y: 1, z: 0.4 },
              },
              autosize: true,
              dragmode: 'turntable',
            }}
            useResizeHandler
            config={{
              scrollZoom: true,
            }}
          />
        </Flex>
        {angularVelocityData.length > 0 && (
          <Plot
            style={{ width: '90%', height: '400px', margin: '5px' }}
            data={angularVelocityData}
            layout={{
              title: 'Angular velocity (body frame)',
              xaxis: { title: 'Time' },
              yaxis: { title: 'Radians per time unit' },
              autosize: true,
            }}
            useResizeHandler
          />
        )}
        <Flex justify="center" width="100%" m="4">
          <Table.Root
            style={{
              width: '800px',
            }}
          >
            {/* Table: https://www.radix-ui.com/themes/docs/components/table */}
            <Table.Header>
              <Table.Row>
                <Table.ColumnHeaderCell>Agent</Table.ColumnHeaderCell>
                <Table.ColumnHeaderCell>Initial Position (x,y, z)</Table.ColumnHeaderCell>
                <Table.ColumnHeaderCell>Initial Velocity (x,y,z)</Table.ColumnHeaderCell>
                <Table.ColumnHeaderCell>CAD Model</Table.ColumnHeaderCell>
              </Table.Row>
            </Table.Header>

            <Table.Body>
              {Object.entries(initialState).flatMap(
                  ([agentId, { position, velocity, model }]) => {
                    if (position) {
                    return (
                <Table.Row key={agentId}>
                  <Table.RowHeaderCell>{agentId}</Table.RowHeaderCell>
                  <Table.Cell>
                    ({position.x}, {position.y}, {position.z})
                  </Table.Cell>
                  <Table.Cell>
                    ({velocity.x}, {velocity.y}, {velocity.z})
                  </Table.Cell>
                  <Table.Cell>
                    {model
                      ? `${model.filename}, ${[model.dimensions.x, model.dimensions.y, model.dimensions.z]
                          .map((d) => Number(d.toPrecision(4)))
                          .join(' × ')}`
                      : 'None (point mass)'}
                  </Table.Cell>
                </Table.Row>
                  );} else {
                    return null;
                  }
                }
              )}
            </Table.Body>
          </Table.Root>
        </Flex>
      </Flex>
    </div>
  );
};

export default App;
