# PWM-PID-Toradex-Public

Source code of the application cannot be shared.

Toradex Colibri VF50 doesn't have digital to analog converter. Delta motors used in this application requires analog voltage for speed control. So, PWM is used to simulate voltage and it's frequency can be varied to control motor speed.

PID control is implemented such that error between target and feedback value is multiplied with an user adjustable gain, to accomodate differences amoong plethora of products.
Integral and Derivative part of the control are not implemented as they're not required at the moment.
