from __future__ import annotations

from typing import Any

import torch
import torch.nn as nn


class ConvLSTMCell(nn.Module):
    """ConvLSTM cell matching both training notebooks."""

    def __init__(self, input_dim: int, hidden_dim: int, kernel_size: int = 3):
        super().__init__()
        padding = kernel_size // 2
        self.conv = nn.Conv2d(
            input_dim + hidden_dim,
            hidden_dim * 4,
            kernel_size,
            padding=padding,
        )

    def forward(
        self,
        x: torch.Tensor,
        h: torch.Tensor,
        c: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        gates = self.conv(torch.cat([x, h], dim=1))
        i, f, o, g = torch.chunk(gates, 4, dim=1)
        c_next = torch.sigmoid(f) * c + torch.sigmoid(i) * torch.tanh(g)
        h_next = torch.sigmoid(o) * torch.tanh(c_next)
        return h_next, c_next


class SingleLayerConvLSTM(nn.Module):
    """Exact state-dict layout used by the Mississippi/UMAP notebook."""

    def __init__(
        self,
        input_dim: int = 2,
        hidden_dim: int = 32,
        output_dim: int = 1,
        dropout_rate: float = 0.25,
        kernel_size: int = 3,
    ):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.encoder_cell = ConvLSTMCell(input_dim, hidden_dim, kernel_size)
        self.decoder_cell = ConvLSTMCell(output_dim, hidden_dim, kernel_size)
        self.output_layer = nn.Conv2d(hidden_dim, output_dim, kernel_size=1)
        self.dropout = nn.Dropout(dropout_rate)

    def forward(self, input_seq: torch.Tensor, pred_len: int) -> torch.Tensor:
        batch, _, _, height, width = input_seq.shape
        h = torch.zeros(batch, self.hidden_dim, height, width, device=input_seq.device)
        c = torch.zeros_like(h)

        for frame in input_seq.unbind(dim=1):
            h, c = self.encoder_cell(frame, h, c)
            if self.training:
                h = self.dropout(h)

        decoder_input = input_seq[:, -1, 0:1]
        outputs = []
        for _ in range(pred_len):
            h, c = self.decoder_cell(decoder_input, h, c)
            decoded = self.dropout(h) if self.training else h
            decoder_input = torch.sigmoid(self.output_layer(decoded))
            outputs.append(decoder_input.unsqueeze(1))
        return torch.cat(outputs, dim=1)


class StackedConvLSTM(nn.Module):
    """Exact state-dict layout used by the Louisiana/WLC hypersearch notebook."""

    def __init__(
        self,
        input_dim: int = 2,
        hidden_dim: int = 16,
        output_dim: int = 1,
        dropout_rate: float = 0.25,
        kernel_size: int = 3,
        num_layers: int = 3,
    ):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers

        encoder_cells = []
        decoder_cells = []
        for layer_index in range(num_layers):
            encoder_input = input_dim if layer_index == 0 else hidden_dim
            decoder_input = output_dim if layer_index == 0 else hidden_dim
            encoder_cells.append(ConvLSTMCell(encoder_input, hidden_dim, kernel_size))
            decoder_cells.append(ConvLSTMCell(decoder_input, hidden_dim, kernel_size))

        self.encoder_cells = nn.ModuleList(encoder_cells)
        self.decoder_cells = nn.ModuleList(decoder_cells)
        self.output_layer = nn.Conv2d(hidden_dim, output_dim, kernel_size=1)
        self.dropout = nn.Dropout(dropout_rate)

    def _states(
        self,
        batch: int,
        height: int,
        width: int,
        device: torch.device,
    ) -> tuple[list[torch.Tensor], list[torch.Tensor]]:
        h = [torch.zeros(batch, self.hidden_dim, height, width, device=device) for _ in range(self.num_layers)]
        c = [torch.zeros_like(state) for state in h]
        return h, c

    def forward(self, input_seq: torch.Tensor, pred_len: int) -> torch.Tensor:
        batch, _, _, height, width = input_seq.shape
        h, c = self._states(batch, height, width, input_seq.device)

        for frame in input_seq.unbind(dim=1):
            layer_input = frame
            for layer_index, cell in enumerate(self.encoder_cells):
                h[layer_index], c[layer_index] = cell(
                    layer_input, h[layer_index], c[layer_index]
                )
                layer_input = self.dropout(h[layer_index]) if self.training else h[layer_index]

        decoder_input = input_seq[:, -1, 0:1]
        outputs = []
        for _ in range(pred_len):
            layer_input = decoder_input
            for layer_index, cell in enumerate(self.decoder_cells):
                h[layer_index], c[layer_index] = cell(
                    layer_input, h[layer_index], c[layer_index]
                )
                layer_input = self.dropout(h[layer_index]) if self.training else h[layer_index]
            decoder_input = torch.sigmoid(self.output_layer(layer_input))
            outputs.append(decoder_input.unsqueeze(1))
        return torch.cat(outputs, dim=1)


def build_model(region: dict[str, Any]) -> nn.Module:
    common = {
        "input_dim": int(region["input_dim"]),
        "hidden_dim": int(region["hidden_dim"]),
        "output_dim": int(region["output_dim"]),
        "dropout_rate": float(region["dropout_rate"]),
        "kernel_size": int(region["kernel_size"]),
    }
    if region["architecture"] == "single_layer":
        return SingleLayerConvLSTM(**common)
    return StackedConvLSTM(**common, num_layers=int(region["num_layers"]))


def load_model(region: dict[str, Any], device: torch.device) -> nn.Module:
    model = build_model(region).to(device)
    state_dict = torch.load(region["model_path"], map_location=device, weights_only=True)
    model.load_state_dict(state_dict, strict=True)
    model.eval()
    return model


@torch.inference_mode()
def predict(
    model: nn.Module,
    processed_values,
    input_len: int,
    pred_len: int,
    device: torch.device,
):
    import numpy as np

    if processed_values.shape[0] != input_len:
        raise ValueError(
            f"Expected exactly {input_len} input days, got {processed_values.shape[0]}"
        )
    array = processed_values.transpose(0, 3, 1, 2).astype(np.float32, copy=False)
    tensor = torch.from_numpy(array).unsqueeze(0).to(device)
    output = model(tensor, pred_len=pred_len)
    return output.squeeze(0).squeeze(1).cpu().numpy()
