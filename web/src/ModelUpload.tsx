import { Button, Flex, Text } from '@radix-ui/themes';
import React, { useCallback, useId, useRef, useState } from 'react';

// Mass properties of an uploaded CAD model, as returned by `POST /models`.
export interface UploadedModel {
  id: number;
  filename: string;
  triangleCount: number;
  volume: number;
  centerOfMass: { x: number; y: number; z: number };
}

interface ModelUploadProps {
  bodyName: string;
  mass: number | '';
  model: UploadedModel | null;
  onChange: (model: UploadedModel | null) => void;
}

const formatNumber = (n: number) => Number(n.toPrecision(6)).toString();

const ModelUpload: React.FC<ModelUploadProps> = ({ bodyName, mass, model, onChange }) => {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      setUploading(true);
      setError(null);
      try {
        const body = new FormData();
        body.append('file', file);
        const response = await fetch('http://localhost:8000/models', { method: 'POST', body });
        const result = await response.json();
        if (!response.ok) {
          throw new Error(result.error ?? 'Upload failed.');
        }
        onChange(result as UploadedModel);
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

  const handleRemove = useCallback(() => {
    setError(null);
    onChange(null);
  }, [onChange]);

  return (
    <Flex direction="column" gap="1" mb="2">
      <label htmlFor={inputId}>
        <Text size="2">CAD model (STL, optional)</Text>
      </label>
      <input
        id={inputId}
        ref={inputRef}
        type="file"
        accept=".stl,model/stl"
        onChange={handleFile}
        disabled={uploading}
        aria-describedby={`${inputId}-status`}
      />
      <div id={`${inputId}-status`} aria-live="polite">
        {uploading && <Text size="1">Computing center of mass…</Text>}
        {error && (
          <Text size="1" color="red" role="alert">
            {error}
          </Text>
        )}
        {model && (
          <Flex direction="column">
            <Text size="1">
              {model.filename}: {model.triangleCount.toLocaleString()} triangles, volume{' '}
              {formatNumber(model.volume)}
              {typeof mass === 'number' && mass > 0 && <>, density {formatNumber(mass / model.volume)}</>}
            </Text>
            <Text size="1">
              Center of mass in model coordinates: ({formatNumber(model.centerOfMass.x)},{' '}
              {formatNumber(model.centerOfMass.y)}, {formatNumber(model.centerOfMass.z)})
            </Text>
            <Text size="1" color="gray">
              {bodyName}'s position below places the model's origin; it is simulated at its center of mass.
            </Text>
            <Flex>
              <Button type="button" size="1" variant="soft" mt="1" onClick={handleRemove}>
                Remove model
              </Button>
            </Flex>
          </Flex>
        )}
      </div>
    </Flex>
  );
};

export default ModelUpload;
