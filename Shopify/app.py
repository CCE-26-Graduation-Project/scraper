import modal
from io import BytesIO

image = (
    modal.Image.debian_slim()
    .pip_install(
        "transformers",
        "torch",
        "Pillow",
    )
)

app = modal.App("clip-service", image=image)


@app.cls(gpu="T4", timeout=600)
class ClipModel:
    @modal.enter()
    def load_model(self):
        from transformers import CLIPProcessor, CLIPModel
        import torch

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(self.device)
        self.processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

    def _to_embedding_list(self, tensor):
        return tensor.squeeze(0).detach().cpu().tolist()

    @modal.method()
    def get_text_embedding(self, text: str):
        inputs = self.processor(text=[text], return_tensors="pt", padding=True).to(self.device)
        outputs = self.model.get_text_features(**inputs)

        if hasattr(outputs, "pooler_output"):
            tensor = outputs.pooler_output
            if hasattr(self.model, "text_projection"):
                tensor = self.model.text_projection(tensor)
        else:
            tensor = outputs

        embedding = tensor.squeeze(0).detach().cpu().tolist()
        return embedding

    @modal.method()
    def get_image_embedding(self, image_bytes: bytes):
        from PIL import Image
        import torch

        image = Image.open(BytesIO(image_bytes))
        inputs = self.processor(images=image, return_tensors="pt").to(self.device)
        outputs = self.model.get_image_features(**inputs)

        if isinstance(outputs, torch.Tensor):
            tensor = outputs
        elif hasattr(outputs, "image_embeds") and outputs.image_embeds is not None:
            tensor = outputs.image_embeds
        elif hasattr(outputs, "pooler_output"):
            tensor = outputs.pooler_output
            # Only project if this is pre-projection size (usually 768)
            if tensor.shape[-1] == self.model.visual_projection.in_features:
                tensor = self.model.visual_projection(tensor)
        else:
            raise ValueError("Unsupported image output type")

        embedding = tensor.squeeze(0).detach().cpu().tolist()
        return embedding