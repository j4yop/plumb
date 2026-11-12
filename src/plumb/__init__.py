"""PLUMB — checking tracking-derived claims, one at a time.

*To plumb something is to find out where it actually stands.*

The Phase 1 engine decides who has the ball on every frame. This package wraps that in the
interface the project is judged by: a question goes in, and either a **supported** answer comes
out carrying its evidence, or a **refusal** does — naming what is missing and what would have to
be collected to answer it.

Nothing here uses a language model. The router is a set of rules over the question, the renderer
is a deterministic formatter over a structured answer, and a refusal is exact. That is deliberate:
the pitch is that the reasoning is deterministic and the claims are reproducible, so the machine
must not be able to invent one.
"""

__all__ = ["analysis", "facts", "router", "cli"]

__version__ = "0.1.0"
