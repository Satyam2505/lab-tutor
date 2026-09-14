<!--
tier: C (curated adjacent — NOT the IACHY102 manual)
experiments: exp03
topic: general Beer-Lambert theory and camera colour science (not manual-specific)
-->

# Colorimetry background: Beer-Lambert law and the smartphone/RGB method

General background for the theory behind the colorimetric and
smartphone-based determination of Ni(II). The manual's own stated
procedure, wavelength/filter choice, and table structure are the
authority for what to actually do and report.

## The Beer-Lambert law, generally

The Beer-Lambert law relates how much light a solution absorbs to its
concentration: A = ε·b·c, where A is absorbance, ε is the molar
absorptivity (a constant specific to the absorbing species and
wavelength), b is the path length of light through the sample (usually
the width of the cuvette), and c is the concentration.

Because A is directly proportional to c (for a fixed species, wavelength
and path length), a plot of absorbance against known concentrations —
the calibration curve — is expected to be linear over the concentration
range where the law holds. Deviations from linearity at high
concentration are common and are generally attributed to effects the
simple law does not capture (e.g. changes in the solution's refractive
index, chemical interactions between solute particles, or stray light in
the instrument at high absorbance) rather than the law itself being
wrong — this is a standard reason a calibration curve is only trusted
within the concentration range it was actually measured over.

## Why colour intensity relates to concentration at all

A coloured complex (such as many transition-metal complexes, including
nickel(II) complexes formed with a suitable reagent) absorbs some
wavelengths of visible light more than others; the wavelengths it does
not absorb are transmitted or reflected, which is what gives it its
observed colour. A more concentrated solution has more absorbing
species in the light's path, so it absorbs more strongly — the physical
basis for using colour intensity as a proxy for concentration in both
a dedicated colorimeter and a smartphone-camera-based method.

## How a smartphone camera captures colour, generally

A camera's image sensor is covered by a filter mosaic (commonly a Bayer
filter) so that each pixel records mostly one of three colour channels —
red, green, and blue. A photo's per-pixel R, G, and B values are the
camera and its software's estimate of how much light in roughly those
three wavelength bands reached that pixel, after substantial internal
processing (white balance, gamma correction, and other adjustments the
camera applies automatically) that a dedicated spectrophotometer does
not perform.

## Why an RGB channel ratio, rather than one channel alone, is often used

A single colour channel's raw value depends on far more than the
sample's concentration — ambient lighting brightness and colour
temperature, the phone's auto-exposure and auto-white-balance decisions,
and the camera's own colour processing all affect it. Taking a ratio
between two channels (e.g. R/G, R/B, or G/B) cancels out some of these
shared confounds, since a change in overall brightness tends to scale
several channels together, while the ratio does not. This is the general
motivation for smartphone colorimetry methods using a channel ratio as
the measured quantity rather than a single raw channel value, though a
ratio does not eliminate every source of variation — controlling
lighting conditions and using a fixed camera setup between the standards
and the unknown sample remains important for a reliable calibration.

## Known limitations of the smartphone/RGB approach, generally

- Automatic camera adjustments (auto-exposure, auto-white-balance, HDR
  processing) can shift results between photos taken under seemingly
  similar conditions, which is why keeping the phone's settings and the
  lighting as consistent as possible between standards and the unknown
  sample matters more here than for a dedicated spectrophotometer.
- The method is generally less precise than a dedicated colorimeter or
  spectrophotometer, which measure absorbance at a specific, narrow
  wavelength band rather than through a much broader, camera-defined
  colour channel.
- Results from one phone's camera are not necessarily transferable to
  another phone's camera without a fresh calibration, since sensors and
  internal image processing differ between devices.

These are general, well-documented limitations of camera-based
colorimetry as a technique; they are background for interpreting your
own results; they are not, by themselves, a diagnosis of any particular
result you obtained; and they should not be used to explain away a
specific unexpected number without also checking your own standards,
dilutions and measurement conditions.
