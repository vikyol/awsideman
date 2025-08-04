#!/usr/bin/env python3
"""
Internal import validation script for awsideman project.

This script validates that all internal import statements in the codebase 
have correct paths after the project packaging reorganization. It focuses
on validating import paths without actually importing modules to avoid
external dependency issues.
"""

import ast
import os
from pathlib import Path
from typing import List, Dict, Set, Tuple


class InternalImportValidator:
    """Validates internal import statements in Python files."""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.src_root = self.project_root / "src" / "awsideman"
        self.test_root = self.project_root / "tests"
        self.broken_imports = []
        self.successful_imports = []
        self.skipped_imports = []
        
    def find_python_files(self) -> List[Path]:
        """Find all Python files in the project."""
        python_files = []
        
        # Find files in src directory
        if self.src_root.exists():
            python_files.extend(self.src_root.rglob("*.py"))
            
        # Find files in tests directory
        if self.test_root.exists():
            python_files.extend(self.test_root.rglob("*.py"))
            
        return python_files
    
    def extract_internal_imports(self, file_path: Path) -> List[Tuple[str, int, str]]:
        """Extract internal import statements from a Python file."""
        imports = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            tree = ast.parse(content, filename=str(file_path))
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        # Only check internal imports (awsideman or relative)
                        if self.is_internal_import(alias.name):
                            imports.append((alias.name, node.lineno, "import"))
                        
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        # Handle "from module import name" statements
                        if self.is_internal_import(node.module):
                            for alias in node.names:
                                if alias.name == "*":
                                    imports.append((node.module, node.lineno, "from_star"))
                                else:
                                    imports.append((f"{node.module}.{alias.name}", node.lineno, "from_import"))
                    else:
                        # Handle relative imports like "from . import name"
                        level = node.level
                        if level > 0:
                            for alias in node.names:
                                imports.append((f"{'.' * level}{alias.name}", node.lineno, "relative"))
                                
        except SyntaxError as e:
            print(f"Syntax error in {file_path}: {e}")
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
            
        return imports
    
    def is_internal_import(self, import_name: str) -> bool:
        """Check if an import is internal to the project."""
        # Check for awsideman imports
        if import_name.startswith("awsideman") or import_name.startswith("src.awsideman"):
            return True
        
        # Check for relative imports (handled separately)
        if import_name.startswith("."):
            return True
            
        return False
    
    def validate_import_path(self, import_name: str, file_path: Path, line_no: int, import_type: str) -> bool:
        """Validate that an import path exists in the file system."""
        
        if import_type == "relative":
            return self.validate_relative_import(import_name, file_path, line_no)
        
        # Handle absolute imports
        if import_name.startswith("src.awsideman"):
            # Remove src. prefix for path resolution
            module_path = import_name[4:]  # Remove "src."
        elif import_name.startswith("awsideman"):
            module_path = import_name
        else:
            self.skipped_imports.append((import_name, str(file_path), line_no, "not_internal"))
            return True
        
        # Convert module path to file path
        parts = module_path.split(".")
        
        if import_type == "from_import":
            # For "from module import name", check if module exists
            module_parts = parts[:-1]  # Remove the imported name
            attr_name = parts[-1]
        else:
            # Direct import
            module_parts = parts
            attr_name = None
        
        # Build the expected file path
        expected_path = self.src_root
        for part in module_parts[1:]:  # Skip "awsideman"
            expected_path = expected_path / part
        
        # Check if it's a package (directory with __init__.py) or module (.py file)
        package_path = expected_path / "__init__.py"
        module_file_path = expected_path.with_suffix(".py")
        
        if package_path.exists():
            # It's a package
            if attr_name and import_type == "from_import":
                # Check if the attribute is likely to exist (basic heuristic)
                if not self.check_attribute_in_package(package_path, attr_name):
                    self.broken_imports.append((import_name, str(file_path), line_no, f"Attribute '{attr_name}' not found in package"))
                    return False
            self.successful_imports.append((import_name, str(file_path), line_no))
            return True
        elif module_file_path.exists():
            # It's a module
            if attr_name and import_type == "from_import":
                # Check if the attribute is likely to exist (basic heuristic)
                if not self.check_attribute_in_module(module_file_path, attr_name):
                    self.broken_imports.append((import_name, str(file_path), line_no, f"Attribute '{attr_name}' not found in module"))
                    return False
            self.successful_imports.append((import_name, str(file_path), line_no))
            return True
        else:
            self.broken_imports.append((import_name, str(file_path), line_no, f"Module/package not found at {expected_path}"))
            return False
    
    def validate_relative_import(self, import_name: str, file_path: Path, line_no: int) -> bool:
        """Validate relative import paths."""
        # Get the directory of the current file
        current_dir = file_path.parent
        
        # Count the dots to determine the level
        level = 0
        for char in import_name:
            if char == '.':
                level += 1
            else:
                break
        
        # Get the module name after the dots
        module_name = import_name[level:]
        
        # Calculate the target directory
        target_dir = current_dir
        for _ in range(level - 1):  # level-1 because one dot means current directory
            target_dir = target_dir.parent
        
        if module_name:
            # Check if the target module exists
            target_path = target_dir / f"{module_name}.py"
            target_package = target_dir / module_name / "__init__.py"
            
            if target_path.exists() or target_package.exists():
                self.successful_imports.append((import_name, str(file_path), line_no))
                return True
            else:
                self.broken_imports.append((import_name, str(file_path), line_no, f"Relative import target not found: {target_path}"))
                return False
        else:
            # Just importing from current package
            init_file = target_dir / "__init__.py"
            if init_file.exists():
                self.successful_imports.append((import_name, str(file_path), line_no))
                return True
            else:
                self.broken_imports.append((import_name, str(file_path), line_no, f"Package __init__.py not found: {init_file}"))
                return False
    
    def check_attribute_in_package(self, package_init_path: Path, attr_name: str) -> bool:
        """Basic check if an attribute is defined in a package's __init__.py."""
        try:
            with open(package_init_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Simple heuristic: check if the attribute name appears in the file
            # This is not perfect but catches most cases
            return attr_name in content
        except Exception:
            return True  # Assume it exists if we can't check
    
    def check_attribute_in_module(self, module_path: Path, attr_name: str) -> bool:
        """Basic check if an attribute is defined in a module."""
        try:
            with open(module_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Simple heuristic: check if the attribute name appears in the file
            # This catches class definitions, function definitions, and variables
            return (f"class {attr_name}" in content or 
                   f"def {attr_name}" in content or 
                   f"{attr_name} =" in content or
                   f"'{attr_name}'" in content or
                   f'"{attr_name}"' in content)
        except Exception:
            return True  # Assume it exists if we can't check
    
    def validate_all_imports(self) -> Dict[str, int]:
        """Validate all internal imports in the project."""
        print("🔍 Finding Python files...")
        python_files = self.find_python_files()
        print(f"Found {len(python_files)} Python files")
        
        print("\n📦 Validating internal imports...")
        total_imports = 0
        
        for file_path in python_files:
            rel_path = file_path.relative_to(self.project_root)
            print(f"  Checking {rel_path}")
            imports = self.extract_internal_imports(file_path)
            total_imports += len(imports)
            
            for import_name, line_no, import_type in imports:
                self.validate_import_path(import_name, file_path, line_no, import_type)
        
        return {
            "total": total_imports,
            "successful": len(self.successful_imports),
            "broken": len(self.broken_imports),
            "skipped": len(self.skipped_imports)
        }
    
    def print_report(self):
        """Print a detailed validation report."""
        stats = {
            "total": len(self.successful_imports) + len(self.broken_imports) + len(self.skipped_imports),
            "successful": len(self.successful_imports),
            "broken": len(self.broken_imports),
            "skipped": len(self.skipped_imports)
        }
        
        print("\n" + "="*80)
        print("📊 INTERNAL IMPORT VALIDATION REPORT")
        print("="*80)
        
        print(f"Total internal imports found: {stats['total']}")
        print(f"✅ Successful imports: {stats['successful']}")
        print(f"❌ Broken imports: {stats['broken']}")
        print(f"⏭️  Skipped imports: {stats['skipped']}")
        
        if stats['broken'] == 0:
            print("\n🎉 All internal imports are valid! No broken import references found.")
        else:
            print(f"\n⚠️  Found {stats['broken']} broken internal imports:")
            print("-" * 80)
            
            for import_name, file_path, line_no, error in self.broken_imports:
                rel_path = Path(file_path).relative_to(self.project_root)
                print(f"❌ {import_name}")
                print(f"   File: {rel_path}:{line_no}")
                print(f"   Error: {error}")
                print()
        
        print("\n" + "="*80)
        
        return stats['broken'] == 0


def main():
    """Main function to run internal import validation."""
    print("🚀 Starting internal import validation for awsideman project")
    
    # Get project root (parent directory of scripts folder)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    # Create validator and run validation
    validator = InternalImportValidator(project_root)
    validator.validate_all_imports()
    
    # Print report and return appropriate exit code
    success = validator.print_report()
    
    if success:
        print("✅ Internal import validation completed successfully!")
        return 0
    else:
        print("❌ Internal import validation failed - broken imports found!")
        return 1


if __name__ == "__main__":
    exit(main())