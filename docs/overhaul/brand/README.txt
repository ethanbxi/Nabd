nab'd brand assets
==================

Generated from the supplied artwork. Paths are unmodified.

THE HORN RULE
-------------
The horns appear exactly once. Whichever element is alone wears them.

  wordmark on its own ....... nabd-wordmark-horned-*
  mark present in a lockup .. nabd-wordmark-plain-*

Every lockup here already uses the plain wordmark. The MARK is never modified —
do not produce a hornless mark.

FILES
-----
  nabd-mark-cream.svg            artwork only, for dark grounds
  nabd-mark-ink.svg              artwork only, for light grounds
  nabd-mark-purple-field.svg     on the #6C3BAA tile -- the primary treatment
  nabd-app-tile-512.svg          the same at icon size; source for icon.ico
  nabd-tray-template.svg         16 px, single colour. NOTE: the silhouette has
                                 horns now -- the old arc template is wrong.

  nabd-wordmark-horned-cream.svg / -ink.svg
  nabd-wordmark-plain-cream.svg  / -ink.svg

  nabd-lockup-cream.svg / -ink.svg / -purple-field.svg
  nabd-stacked-cream.svg / -ink.svg / -purple-field.svg

COLOUR
------
  field  #6C3BAA   fills only
  cream  #E8E4DC   artwork on dark
  ink    #0A0A0C   artwork on light

#6C3BAA measures 2.7:1 on the near-black shell. It is a FILL. Anything that has
to be seen -- text, icons, meters, focus rings -- uses #9B6BD8.

EDITING
-------
The wordmark's letters are STROKED paths (19.5, round caps), not outlines. That
is deliberate: it keeps the type in the same geometric family as the mark.
Scaling in Illustrator changes the apparent weight unless "Scale Strokes &
Effects" is on. Outline on a copy if a vendor needs it.

The mark's ring is a filled outline of an arc with a 64.7 degree bite at
4 o'clock. Do not close it, and do not rotate the mark -- a rotating ring buffer
is a loading spinner.
