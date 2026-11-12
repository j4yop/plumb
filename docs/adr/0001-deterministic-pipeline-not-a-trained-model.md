# A deterministic pipeline, not a trained model

There is no permitted training signal for the provided match: the labels we are scored on are
private, and the organisers forbid hand labels on the provided match for training or validation
alike. A trained model would therefore have to be trained on something we are not allowed to
label, so the Phase 1 system is a deterministic algorithm whose every threshold is a football
quantity in metres or seconds. The consequence is that the pipeline has no randomness and no
fitted parameters: the same input always produces the same file, byte for byte.
