import { Form, FormField, FormLabel } from '@radix-ui/react-form';
import { Button, Card, Flex, Heading, Separator, Text, TextField } from '@radix-ui/themes';
import _ from 'lodash';
import React, { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Routes } from 'routes';
import ModelUpload, { BodyModel } from './ModelUpload';
import { API_URL } from 'api';

type FormValue = number | '';
interface FormData {
  Body1: {
    position: {
      x: FormValue;
      y: FormValue;
      z: FormValue;
    }
    velocity: {
      x: FormValue;
      y: FormValue;
      z: FormValue;
    }
    mass: FormValue;
  };
  Body2: {
    position: {
      x: FormValue;
      y: FormValue;
      z: FormValue;
    }
    velocity: {
      x: FormValue;
      y: FormValue;
      z: FormValue;
    }
    mass: FormValue;
  };
}

type BodyName = keyof FormData;

const SimulateForm: React.FC = () => {
  const navigate = useNavigate();
  const [models, setModels] = useState<Record<BodyName, BodyModel | null>>({ Body1: null, Body2: null });
  const setBody1Model = useCallback((model: BodyModel | null) => setModels((prev) => ({ ...prev, Body1: model })), []);
  const setBody2Model = useCallback((model: BodyModel | null) => setModels((prev) => ({ ...prev, Body2: model })), []);

  const [submitError, setSubmitError] = useState<string | null>(null);
  const [formData, setFormData] = useState<FormData>({
    Body1: { position: {x: -0.73, y: 0, z: 0}, velocity: {x: 0, y: -0.0015, z: 0}, mass: 1 },
    Body2: { position: {x: 60.34, y: 0, z: 0}, velocity: {x: 0, y: 0.13, z: 0}, mass: 0.0123 },
  });

  const handleChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    let newValue: FormValue = value === '' ? '' : parseFloat(value);
    setFormData((prev) => _.set({ ...prev }, name, newValue));
  }, []);

  const [submitting, setSubmitting] = useState(false);

  // A file dropped outside the drop zones would otherwise make the browser open it, leaving the form.
  useEffect(() => {
    const ignoreFileDrop = (e: DragEvent) => {
      if (e.dataTransfer?.types.includes('Files')) e.preventDefault();
    };
    window.addEventListener('dragover', ignoreFileDrop);
    window.addEventListener('drop', ignoreFileDrop);
    return () => {
      window.removeEventListener('dragover', ignoreFileDrop);
      window.removeEventListener('drop', ignoreFileDrop);
    };
  }, []);

  // The form blocks submission while any field is empty or invalid, without saying so. Name the
  // fields instead, so a click on Submit never silently does nothing.
  const reportInvalidFields = useCallback((e: React.MouseEvent<HTMLButtonElement>) => {
    const form = e.currentTarget.form;
    if (!form || form.checkValidity()) return;
    const names = Array.from(form.querySelectorAll<HTMLInputElement>('input:invalid')).map((input) => {
      // Model inputs carry an aria-label that already names the body; the plain fields are labelled
      // like "Mass", so prefix the body from their name ("Body1.mass").
      const ariaLabel = input.getAttribute('aria-label');
      if (ariaLabel) return ariaLabel;
      const label = form.querySelector(`label[for="${CSS.escape(input.id)}"]`)?.textContent ?? input.name;
      return `${input.name.split('.')[0]} ${label}`;
    });
    setSubmitError(`Fix these fields before submitting: ${names.join(', ')}.`);
  }, []);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setSubmitError(null);
      setSubmitting(true);
      try {
        const response = await fetch(`${API_URL}/simulation`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          // A body with an uploaded model is simulated as that rigid body, scaled to `size`.
          body: JSON.stringify(
            _.mapValues(formData, (body, name) => {
              const attached = models[name as BodyName];
              return attached
                ? {
                    ...body,
                    modelId: attached.model.id,
                    size: attached.size,
                    angularVelocity: attached.angularVelocity,
                    orientation: attached.orientation,
                  }
                : body;
            })
          ),
        });
        if (!response.ok) {
          // The API explains its own errors; anything else (e.g. the dev server could not reach the
          // backend) only has a status code.
          const result = await response.json().catch(() => ({}));
          throw new Error(
            result.error ?? `The server returned an error (HTTP ${response.status}). Check that the backend is running and see its logs.`
          );
        }
        navigate(Routes.SIMULATION);
      } catch (error) {
        console.error('Error:', error);
        setSubmitError(error instanceof Error ? error.message : 'Simulation failed.');
      } finally {
        setSubmitting(false);
      }
    },
    [formData, models]
  );

  return (
    <div
      style={{
        position: 'absolute',
        top: '5%',
        left: 'calc(50% - 200px)',
        overflow: 'scroll',
      }}
    >
      {/* Card: https://www.radix-ui.com/themes/docs/components/card */}
      <Card
        style={{
          width: '400px',
        }}
      >
        <Heading as="h2" size="4" weight="bold" mb="4">
          Run a Simulation
        </Heading>
        <Link to={Routes.SIMULATION}>View previous simulation</Link>
        <Separator size="4" my="5" />
        <Form onSubmit={handleSubmit}>
          {/* 
            *********************************
            Body1
            *********************************
            */}
          <Heading as="h3" size="3" weight="bold">
            Body1
          </Heading>
          <ModelUpload bodyName="Body1" mass={formData.Body1.mass} value={models.Body1} onChange={setBody1Model} />
          {/* Form: https://www.radix-ui.com/primitives/docs/components/form */}
          <FormField name="Body1.position.x">
            <FormLabel htmlFor="Body1.position.x">Initial X-position{models.Body1 && ' of model origin'}</FormLabel>
            <TextField.Root
              type="number"
              id="Body1.position.x"
              name="Body1.position.x"
              value={formData.Body1.position.x}
              onChange={handleChange}
              required
            />
          </FormField>
          <FormField name="Body1.position.y">
            <FormLabel htmlFor="Body1.position.y">Initial Y-position{models.Body1 && ' of model origin'}</FormLabel>
            <TextField.Root
              type="number"
              id="Body1.position.y"
              name="Body1.position.y"
              value={formData.Body1.position.y}
              onChange={handleChange}
              required
            />
          </FormField>
          <FormField name="Body1.position.z">
            <FormLabel htmlFor="Body1.position.z">Initial Z-position{models.Body1 && ' of model origin'}</FormLabel>
            <TextField.Root
              type="number"
              id="Body1.position.z"
              name="Body1.position.z"
              value={formData.Body1.position.z}
              onChange={handleChange}
              required
            />
          </FormField>
          <FormField name="Body1.velocity.x">
            <FormLabel htmlFor="Body1.velocity.x">Initial X-velocity</FormLabel>
            <TextField.Root
              type="number"
              id="Body1.velocity.x"
              name="Body1.velocity.x"
              value={formData.Body1.velocity.x}
              onChange={handleChange}
              required
            />
          </FormField>
          <FormField name="Body1.velocity.y">
            <FormLabel htmlFor="Body1.velocity.y">Initial Y-velocity</FormLabel>
            <TextField.Root
              type="number"
              id="Body1.velocity.y"
              name="Body1.velocity.y"
              value={formData.Body1.velocity.y}
              onChange={handleChange}
              required
            />
          </FormField>
          <FormField name="Body1.velocity.z">
            <FormLabel htmlFor="Body1.velocity.z">Initial Z-velocity</FormLabel>
            <TextField.Root
              type="number"
              id="Body1.velocity.z"
              name="Body1.velocity.z"
              value={formData.Body1.velocity.z}
              onChange={handleChange}
              required
            />
          </FormField>
          <FormField name="Body1.mass">
            <FormLabel htmlFor="Body1.mass">Mass</FormLabel>
            <TextField.Root
              type="number"
              id="Body1.mass"
              name="Body1.mass"
              value={formData.Body1.mass}
              onChange={handleChange}
              required
            />
          </FormField>
          {/* 
            *********************************
            Body2
            *********************************
             */}
          <Heading as="h3" size="3" weight="bold" mt="4">
            Body2
          </Heading>
          <ModelUpload bodyName="Body2" mass={formData.Body2.mass} value={models.Body2} onChange={setBody2Model} />
          <FormField name="Body2.position.x">
            <FormLabel htmlFor="Body2.position.x">Initial X-position{models.Body2 && ' of model origin'}</FormLabel>
            <TextField.Root
              type="number"
              id="Body2.position.x"
              name="Body2.position.x"
              value={formData.Body2.position.x}
              onChange={handleChange}
              required
            />
          </FormField>
          <FormField name="Body2.position.y">
            <FormLabel htmlFor="Body2.position.y">Initial Y-position{models.Body2 && ' of model origin'}</FormLabel>
            <TextField.Root
              type="number"
              id="Body2.position.y"
              name="Body2.position.y"
              value={formData.Body2.position.y}
              onChange={handleChange}
              required
            />
          </FormField>
          <FormField name="Body2.position.z">
            <FormLabel htmlFor="Body2.position.z">Initial Z-position{models.Body2 && ' of model origin'}</FormLabel>
            <TextField.Root
              type="number"
              id="Body2.position.z"
              name="Body2.position.z"
              value={formData.Body2.position.z}
              onChange={handleChange}
              required
            />
          </FormField>
          <FormField name="Body2.velocity.x">
            <FormLabel htmlFor="Body2.velocity.x">Initial X-velocity</FormLabel>
            <TextField.Root
              type="number"
              id="Body2.velocity.x"
              name="Body2.velocity.x"
              value={formData.Body2.velocity.x}
              onChange={handleChange}
              required
            />
          </FormField>
          <FormField name="Body2.velocity.y">
            <FormLabel htmlFor="Body2.velocity.y">Initial Y-velocity</FormLabel>
            <TextField.Root
              type="number"
              id="Body2.velocity.y"
              name="Body2.velocity.y"
              value={formData.Body2.velocity.y}
              onChange={handleChange}
              required
            />
          </FormField>
          <FormField name="Body2.velocity.z">
            <FormLabel htmlFor="Body2.velocity.z">Initial Z-velocity</FormLabel>
            <TextField.Root
              type="number"
              id="Body2.velocity.z"
              name="Body2.velocity.z"
              value={formData.Body2.velocity.z}
              onChange={handleChange}
              required
            />
          </FormField>
          <FormField name="Body2.mass">
            <FormLabel htmlFor="Body2.mass">Mass</FormLabel>
            <TextField.Root
              type="number"
              id="Body2.mass"
              name="Body2.mass"
              value={formData.Body2.mass}
              onChange={handleChange}
              required
            />
          </FormField>
          <Flex direction="column" align="center" gap="2" m="5">
            <Button type="submit" disabled={submitting} onClick={reportInvalidFields}>
              {submitting ? 'Running simulation…' : 'Submit'}
            </Button>
            {submitError && (
              <Text size="2" color="red" role="alert">
                {submitError}
              </Text>
            )}
          </Flex>
        </Form>
      </Card>
    </div>
  );
};

export default SimulateForm;
