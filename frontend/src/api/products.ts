import { getJson } from "./client";
import { loadOverview } from "./overview";
import type { ChangeEvent, Product, Site } from "../types/api";

export type ProductDetailContext = {
  product: Product | null;
  products: Product[];
  events: ChangeEvent[];
  sites: Site[];
  live: boolean;
  mode: "live" | "demo";
  message: string;
};

export function loadProducts(siteId?: number): Promise<Product[]> {
  const query = siteId ? `?site_id=${siteId}` : "";
  return getJson<Product[]>(`/api/products${query}`);
}

export async function loadProductDetailContext(productId: number | string): Promise<ProductDetailContext> {
  const overview = await loadOverview();
  const product = overview.products.find((item) => String(item.id) === String(productId)) || null;
  const events = overview.events.filter((event) => {
    if (!product) return false;
    return event.product_id === product.id
      || (!!event.product_url && event.product_url === product.url)
      || (!!event.product_title && event.product_title === product.title);
  });

  return {
    product,
    products: overview.products,
    events,
    sites: overview.sites,
    live: overview.live,
    mode: overview.mode,
    message: overview.message,
  };
}
