import { afterEach, describe, expect, it, vi } from "vitest";

const apiUploadFile = vi.fn();
const apiFetchBlob = vi.fn();
const apiClientGet = vi.fn();

vi.mock("@/lib/api-client", () => ({
  apiClient: { get: (...args: unknown[]) => apiClientGet(...args) },
  apiUploadFile: (...args: unknown[]) => apiUploadFile(...args),
  apiFetchBlob: (...args: unknown[]) => apiFetchBlob(...args),
}));

const { laboratoryApi } = await import("./laboratory-api");

describe("laboratoryApi.uploadAttachment", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("sends the real file bytes as multipart/form-data, not just metadata", async () => {
    const file = new File(["fake-image-bytes"], "cbc-result.jpg", { type: "image/jpeg" });
    apiUploadFile.mockResolvedValueOnce({
      id: "att-1",
      attachment_type: "Image",
      file_name: "cbc-result.jpg",
      file_url: "/laboratory/orders/order-1/attachments/att-1/file",
      file_size_bytes: 17,
      uploaded_by: "user-1",
      created_at: "2026-01-01T00:00:00Z",
    });

    const result = await laboratoryApi.uploadAttachment("order-1", { file, attachmentType: "Image" });

    expect(apiUploadFile).toHaveBeenCalledTimes(1);
    const [path, formData] = apiUploadFile.mock.calls[0] as [string, FormData];
    expect(path).toBe("/laboratory/orders/order-1/attachments");
    expect(formData).toBeInstanceOf(FormData);
    expect(formData.get("attachment_type")).toBe("Image");
    const sentFile = formData.get("file");
    expect(sentFile).toBeInstanceOf(File);
    expect((sentFile as File).name).toBe("cbc-result.jpg");

    expect(result).toEqual({
      id: "att-1",
      attachmentType: "Image",
      fileName: "cbc-result.jpg",
      fileUrl: "/laboratory/orders/order-1/attachments/att-1/file",
      fileSizeBytes: 17,
      uploadedBy: "user-1",
      createdAt: "2026-01-01T00:00:00Z",
    });
  });

  it("defaults attachment_type to Image when none is given", async () => {
    const file = new File(["bytes"], "scan.png", { type: "image/png" });
    apiUploadFile.mockResolvedValueOnce({
      id: "att-2", attachment_type: "Image", file_name: "scan.png",
      file_url: "/laboratory/orders/order-1/attachments/att-2/file", file_size_bytes: 5,
      uploaded_by: null, created_at: "2026-01-01T00:00:00Z",
    });

    await laboratoryApi.uploadAttachment("order-1", { file });

    const [, formData] = apiUploadFile.mock.calls[0] as [string, FormData];
    expect(formData.get("attachment_type")).toBe("Image");
  });
});

describe("laboratoryApi.listAttachments", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("maps snake_case attachment rows to camelCase", async () => {
    apiClientGet.mockResolvedValueOnce([
      {
        id: "att-1", attachment_type: "Image", file_name: "cbc-result.jpg",
        file_url: "/laboratory/orders/order-1/attachments/att-1/file", file_size_bytes: 999,
        uploaded_by: "user-1", created_at: "2026-01-01T00:00:00Z",
      },
    ]);

    const result = await laboratoryApi.listAttachments("order-1");

    expect(apiClientGet).toHaveBeenCalledWith("/laboratory/orders/order-1/attachments");
    expect(result).toEqual([
      {
        id: "att-1", attachmentType: "Image", fileName: "cbc-result.jpg",
        fileUrl: "/laboratory/orders/order-1/attachments/att-1/file", fileSizeBytes: 999,
        uploadedBy: "user-1", createdAt: "2026-01-01T00:00:00Z",
      },
    ]);
  });
});

describe("laboratoryApi.getAttachmentFileBlob", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("fetches the authenticated file URL as a Blob", async () => {
    const blob = new Blob(["bytes"], { type: "image/jpeg" });
    apiFetchBlob.mockResolvedValueOnce(blob);

    const result = await laboratoryApi.getAttachmentFileBlob("/laboratory/orders/order-1/attachments/att-1/file");

    expect(apiFetchBlob).toHaveBeenCalledWith("/laboratory/orders/order-1/attachments/att-1/file");
    expect(result).toBe(blob);
  });
});
