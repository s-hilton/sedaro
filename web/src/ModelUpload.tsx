import { Button, Flex, Text, TextField } from '@radix-ui/themes';
import React, { useCallback, useId, useRef, useState } from 'react';
import { API_URL } from 'api';

type Vector = { x: number; y: number; z: number };
type FormValue = number | '';

// Mass properties of an uploaded CAD model in its own (unitless) STL coordinates, as returned by
// `POST /models`.
export interface UploadedModel {
  id: number;
  filename: string;
  triangleCount: number;
  volume: number;
  centerOfMass: Vector;
  dimensions: Vector;
}

// A model attached to a body, with how it should be sized and spun in the simulation.
export interface BodyModel {
  model: UploadedModel;
  size: FormValue; // longest dimension, in simulation length units
  angularVelocity: { x: FormValue; y: FormValue; z: FormValue }; // body frame, radians per time unit
  orientation: { yaw: FormValue; pitch: FormValue; roll: FormValue }; // degrees, Z-Y-X order
}

interface ModelUploadProps {
  bodyName: string;
  mass: FormValue;
  value: BodyModel | null;
  onChange: (value: BodyModel | null) => void;
}

const formatNumber = (n: number) => Number(n.toPrecision(4)).toString();
const longestDimension = (model: UploadedModel) => Math.max(model.dimensions.x, model.dimensions.y, model.dimensions.z);
const parse = (value: string): FormValue => (value === '' ? '' : parseFloat(value));

const ModelUpload: React.FC<ModelUploadProps> = ({ bodyName, mass, value, onChange }) => {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [dragging, setDragging] = useState(false);

  const uploadFile = useCallback(
    async (file: File) => {
      if (!file.name.toLowerCase().endsWith('.stl')) {
        setError(`${file.name} is not an STL file. Drop or choose a file ending in .stl.`);
        return;
      }
      setUploading(true);
      setError(null);
      try {
        const body = new FormData();
        body.append('file', file);
        const response = await fetch(`${API_URL}/models`, { method: 'POST', body });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(result.error ?? `Upload failed (HTTP ${response.status}). Check that the backend is running.`);
        }
        const model = result as UploadedModel;
        // Start at the file's own size; the user rescales it to simulation units.
        onChange({
          model,
          size: longestDimension(model),
          angularVelocity: { x: 0, y: 0, z: 0 },
          orientation: { yaw: 0, pitch: 0, roll: 0 },
        });
      } catch (err) {
        onChange(null);
        setError(err instanceof Error ? err.message : 'Upload failed.');
      } finally {
        setUploading(false);
        // Allow re-selecting the same file after fixing it.
        if (inputRef.current) inputRef.current.value = '';
      }
    },
    [onChange]
  );

  const handleFile = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) uploadFile(file);
    },
    [uploadFile]
  );

  // Drag and drop: the zone accepts files dragged in from the computer, highlighted while hovered.
  const handleDragOver = useCallback(
    (e: React.DragEvent) => {
      if (!e.dataTransfer.types.includes('Files')) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = uploading ? 'none' : 'copy';
      setDragging(true);
    },
    [uploading]
  );

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    // Moving between children of the zone also fires dragleave; only clear when leaving the zone.
    if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files[0];
      if (file && !uploading) uploadFile(file);
    },
    [uploadFile, uploading]
  );

  const handleRemove = useCallback(() => {
    setError(null);
    onChange(null);
  }, [onChange]);

  const scale = value && typeof value.size === 'number' && value.size > 0 ? value.size / longestDimension(value.model) : null;

  return (
    <Flex direction="column" gap="1" mb="2">
      <label htmlFor={inputId}>
        <Text size="2">CAD model (STL, optional)</Text>
      </label>
      <div
        data-testid={`${bodyName}-drop-zone`}
        onDragEnter={handleDragOver}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 6,
          padding: 12,
          borderRadius: 'var(--radius-3)',
          border: `2px dashed ${dragging ? 'var(--accent-9)' : 'var(--gray-7)'}`,
          background: dragging ? 'var(--accent-a3)' : 'transparent',
          transition: 'background 120ms, border-color 120ms',
        }}
      >
        <Text size="1" color="gray">
          {dragging ? `Drop to attach it to ${bodyName}` : 'Drag an STL file here, or choose one:'}
        </Text>
        <input
          id={inputId}
          ref={inputRef}
          type="file"
          accept=".stl,model/stl"
          onChange={handleFile}
          disabled={uploading}
          aria-describedby={`${inputId}-status`}
        />
      </div>
      <div id={`${inputId}-status`} aria-live="polite">
        {uploading && <Text size="1">Computing mass properties…</Text>}
        {error && (
          <Text size="1" color="red" role="alert">
            {error}
          </Text>
        )}
      </div>
      {value && (
        <Flex direction="column" gap="1">
          <Text size="1">
            {value.model.filename}: {value.model.triangleCount.toLocaleString()} triangles,{' '}
            {formatNumber(value.model.dimensions.x)} × {formatNumber(value.model.dimensions.y)} ×{' '}
            {formatNumber(value.model.dimensions.z)} in file units
          </Text>
          <label htmlFor={`${inputId}-size`}>
            <Text size="2">Size: longest dimension in simulation units</Text>
          </label>
          <TextField.Root
            id={`${inputId}-size`}
            type="number"
            min="0"
            step="any"
            required
            value={value.size}
            onChange={(e) => onChange({ ...value, size: parse(e.target.value) })}
          />
          {scale !== null && (
            <Text size="1">
              Simulated as {formatNumber(scale * value.model.dimensions.x)} × {formatNumber(scale * value.model.dimensions.y)} ×{' '}
              {formatNumber(scale * value.model.dimensions.z)}, volume {formatNumber(scale ** 3 * value.model.volume)}
              {typeof mass === 'number' && mass > 0 && <>, density {formatNumber(mass / (scale ** 3 * value.model.volume))}</>}.
              Center of mass is ({formatNumber(scale * value.model.centerOfMass.x)}, {formatNumber(scale * value.model.centerOfMass.y)},{' '}
              {formatNumber(scale * value.model.centerOfMass.z)}) from the model origin.
            </Text>
          )}
          <Text size="2" id={`${inputId}-orientation`}>
            Initial orientation (degrees)
          </Text>
          <Flex gap="2" role="group" aria-labelledby={`${inputId}-orientation`}>
            {(['yaw', 'pitch', 'roll'] as const).map((angle) => (
              <TextField.Root
                key={angle}
                type="number"
                step="any"
                required
                aria-label={`${bodyName} initial ${angle} in degrees`}
                value={value.orientation[angle]}
                onChange={(e) => onChange({ ...value, orientation: { ...value.orientation, [angle]: parse(e.target.value) } })}
              >
                <TextField.Slot>{angle}</TextField.Slot>
              </TextField.Root>
            ))}
          </Flex>
          <Text size="1" color="gray">
            Turns the model from the simulation axes: yaw about z, then pitch about the new y, then roll about the new x.
          </Text>
          <Text size="2">Initial angular velocity (model axes, radians per time unit)</Text>
          <Flex gap="2">
            {(['x', 'y', 'z'] as const).map((axis) => (
              <TextField.Root
                key={axis}
                type="number"
                step="any"
                required
                aria-label={`${bodyName} initial angular velocity about model ${axis}-axis`}
                value={value.angularVelocity[axis]}
                onChange={(e) => onChange({ ...value, angularVelocity: { ...value.angularVelocity, [axis]: parse(e.target.value) } })}
              >
                <TextField.Slot>{axis}</TextField.Slot>
              </TextField.Root>
            ))}
          </Flex>
          <Text size="1" color="gray">
            {bodyName} is a uniform-density rigid body. The position below places the model's origin; its shape affects its
            gravity and makes it rotate.
          </Text>
          <Flex>
            <Button type="button" size="1" variant="soft" onClick={handleRemove}>
              Remove model
            </Button>
          </Flex>
        </Flex>
      )}
    </Flex>
  );
};

export default ModelUpload;
