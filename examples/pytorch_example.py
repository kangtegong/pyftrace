"""
Train a small network with PyTorch to fit sin(x).

    $ pip install torch
    $ pyftrace -d 3 examples/pytorch_example.py

The trace shows how the training is put together: main() runs a few
epochs, an epoch is a number of training steps, and every step makes a
batch and runs the model.  forward() is never called by this file.  It
appears in the trace because PyTorch calls it when the model is called.

    $ pyftrace -r examples/pytorch_example.py     # where does time go?
    $ pyftrace -f train_step -n 20 examples/pytorch_example.py
    $ pyftrace -v -d 4 -n 60 examples/pytorch_example.py # into PyTorch

See torch_example.py for the same task written without torch.nn.
"""
import math

import torch
from torch import nn

class Regressor(nn.Module):
    def __init__(self, hidden_size):
        super().__init__()
        self.layers = nn.Sequential(
            nn.Linear(1, hidden_size),
            nn.Tanh(),
            nn.Linear(hidden_size, 1),
        )

    def forward(self, x):
        return self.layers(x)

def make_batch(batch_size):
    x = (torch.rand(batch_size, 1) * 2 - 1) * math.pi
    return x, torch.sin(x)

def train_step(model, optimizer, loss_fn, batch_size):
    x, y = make_batch(batch_size)
    optimizer.zero_grad()
    loss = loss_fn(model(x), y)
    loss.backward()
    optimizer.step()
    return round(loss.item(), 4)

def train_epoch(model, optimizer, loss_fn, steps, batch_size):
    losses = []
    for _ in range(steps):
        losses.append(train_step(model, optimizer, loss_fn, batch_size))
    return round(sum(losses) / len(losses), 4)

def evaluate(model, loss_fn):
    x, y = make_batch(256)
    with torch.no_grad():
        return round(loss_fn(model(x), y).item(), 4)

def main():
    torch.manual_seed(0)
    model = Regressor(hidden_size=16)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.05)
    loss_fn = nn.MSELoss()

    for epoch in range(3):
        loss = train_epoch(model, optimizer, loss_fn, steps=4, batch_size=64)
        print(f"epoch {epoch}: loss {loss}")
    print(f"evaluation loss: {evaluate(model, loss_fn)}")

if __name__ == "__main__":
    main()
