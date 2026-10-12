# Asset provenance

The logo system is original SVG path artwork created for this project. All wordmark letters are outlined; there are no runtime font dependencies. SVG and PNG exports are in `public/logos`, with three distinct concepts. See `public/logos/BRAND.md`.

The hero was created with the built-in image-generation tool for this project. It is an illustrative fictional unbranded vehicle, not a photograph of a customer car or evidence of Protune's work. There is no third-party stock licensing dependency. As with any new brand artwork, obtain any trademark clearance the business requires before mass signage production.

Prompt used:

> Use case: ads-marketing. Asset: website hero for premium black and gold car detailing business. Create an extremely photorealistic low front three-quarter studio product photograph of a sleek unbranded dark graphite luxury sports coupe, nose facing left, entire car visible, wide 1536x1024 composition. Car placed in center bottom half, subtle warm gold rim light tracing roof and side, crisp thin white headlights, beautiful silver wheels, black polished studio floor with restrained reflection, pure near-black background. Premium dramatic automotive campaign photography, realistic proportions, no logos, no badges, no text, no number plates with text, no watermark. Background edges very dark #08090b so blends into website. This is an illustrative fictional vehicle, not a specific automaker.

Project assets: `public/assets/hero-car.webp` (1536 × 1024) and `public/assets/hero-car-small.webp` (800 × 533). Responsive source selection, compressed WebP, and a single transform animation avoid a video download or WebGL dependency. The final image was inspected. Pillow was used only for WebP encoding and size optimisation.
