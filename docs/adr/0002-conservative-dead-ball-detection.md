# Dead-ball detection is deliberately conservative

We detect dead ball from the ball being untracked and almost nobody running (96 % precise, about
28 % recall), and we do not try to recover the rest. The reason is the metric's error asymmetry: a
false dead-ball period splits a real possession into two — one true match and one spurious — while
a missed one only makes a possession slightly too long, which temporal IoU forgives. Every
higher-recall rule we measured (40–55 % precision) costs more than it earns. The limitation is
recorded in the technical document rather than hidden.
