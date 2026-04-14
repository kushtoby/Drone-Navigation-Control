#!/usr/bin/env python3
from __future__ import annotations

import numpy as np

try:
    from tensorflow import lite as tflite  # type: ignore
except Exception:  # pragma: no cover
    tflite = None
    try:
        from tflite_runtime.interpreter import Interpreter  # type: ignore
    except Exception:
        Interpreter = None
else:
    Interpreter = None


class KeyPointClassifier:
    def __init__(self, model_path: str, num_threads: int = 1) -> None:
        if tflite is not None:
            self.interpreter = tflite.Interpreter(model_path=model_path, num_threads=num_threads)
        elif Interpreter is not None:
            self.interpreter = Interpreter(model_path=model_path, num_threads=num_threads)
        else:
            raise RuntimeError('No TFLite interpreter is available.')

        self.interpreter.allocate_tensors()
        self.input_details = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()

    def __call__(self, landmark_list):
        input_tensor_index = self.input_details[0]['index']
        self.interpreter.set_tensor(input_tensor_index, np.array([landmark_list], dtype=np.float32))
        self.interpreter.invoke()
        output_tensor_index = self.output_details[0]['index']
        result = self.interpreter.get_tensor(output_tensor_index)
        return int(np.argmax(np.squeeze(result)))
