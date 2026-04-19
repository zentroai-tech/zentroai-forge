/**
 * Types for Tool Contracts API
 */

export interface ToolContractSummary {
  name: string;
  version: string;
  description: string;
  contract_only: boolean;
  auth_type: string;
  has_network_scope: boolean;
  has_data_scope: boolean;
}
