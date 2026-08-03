# Verified Product Identity Design

## Goal

Create a trustworthy cross-site product identity foundation for future price matrices by matching only exact, inspectable identifiers.

## Scope

- Extract and persist Shopify product IDs, variant SKUs, and GTIN/barcode values when present.
- Add a normalized identifier table linked to individual product records.
- Create a match group only when the same cross-site GTIN or SKU is present on products from different sites in the same user workspace.
- Expose each product's identifiers and match group through an owner-authorized API.
- Do not use product title, image, description, embeddings, or fuzzy string similarity to create a match.

## Identifier Rules

| Identifier | Persistence purpose | Automatic cross-site match |
|---|---|---|
| `gtin` / barcode | Global retail identity | Yes, exact normalized value |
| SKU | Supplier or merchant product identity | Yes, exact normalized value |
| Shopify product ID | Stable identity within a Shopify store | No; retained for provenance only |
| Shopify variant ID | Stable identity within a Shopify store | No; retained for provenance only |

Normalization removes surrounding whitespace, uppercases SKU values, and retains only digits for GTIN/barcode values. Empty values are never stored.

## Data Model

- `product_identifiers`: `(product_id, identifier_type, normalized_value, raw_value, provenance)` with a unique product/type/value constraint.
- `product_match_groups`: a workspace-owned canonical group with `identifier_type` and `normalized_value` explaining why the group exists.
- `product_match_members`: joins products to a group, with a unique product/group constraint.

For the first version, a group contains only products from distinct sites. If an identifier appears on only one site, it is stored but no group is created.

## Flow

1. Structured Shopify extraction returns product and variant identifiers with its product data.
2. Product persistence synchronizes identifiers after saving the product and variants.
3. The matcher finds exact identifier values across a user's sites, creates or updates the explainable group, and adds each product member.
4. An API returns group identity, member product details, price, availability, site, and the exact evidence identifier.

## Error Handling and Safety

- Missing or malformed identifiers are ignored instead of guessed.
- Existing products and their events continue to persist even if identifier synchronization fails; the scan worker records the error through its existing failure path.
- The API remains owner-scoped through the member product's site.

## Acceptance Criteria

1. Two products at different sites with matching normalized GTIN or SKU appear in one group with the identifier shown as evidence.
2. Products with only matching titles are never grouped.
3. Platform IDs appear in product identity records but cannot create cross-site groups.
4. A user cannot read another user's matched products or identifiers.
