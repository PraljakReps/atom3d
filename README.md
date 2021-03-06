# ATOM3D: Tasks On Molecules in 3 Dimensions

[![Documentation
Status](https://readthedocs.org/projects/atom3d/badge/?version=latest)](http://atom3d.readthedocs.io/?badge=latest)
![Package](https://github.com/drorlab/atom3d/workflows/package/badge.svg)

[ATOM3D](https://www.atom3d.ai/) enables machine learning on three-dimensional molecular structure.

## Features

* Access to several datasets involving 3D molecular structure. 
* Sharded data format for storing lots of molecules (and associated metadata).
* Utilities for splitting/filtering data based on many criteria.


## Reference

We provide an overview on ATOM3D and details on the preparation of all datasets in our preprint:

> R. J. L. Townshend, M. Vögele, P. Suriana, A. Derry, A. Powers, Y. Laloudakis, S. Balachandar, B. Anderson, S. Eismann, R. Kondor, R. B. Altman, R. O. Dror "ATOM3D: Tasks On Molecules in Three Dimensions", [arXiv:2012.04035](https://arxiv.org/abs/2012.04035)
  
Please cite this work if some of the ATOM3D code or datasets are helpful in your scientific endeavours. For specific datasets, please also cite the respective original source(s), given in the preprint.


## Installation

Install with:

```
make requirements
```
    
To use rdkit functionality, please install within conda:

```
conda create -n atom3d python=3.6 pip rdkit
conda activate atom3d
make requirements
```

## Usage

### LMDB datasets

LMDB allows for compressed, fast, random access to your structures, all within a
single database.  Currently, we support creating LMDB datasets from PDB files, silent files, and xyz files.

#### Creating an LMDB dataset

From command line:
```
python -m atom3d.datasets PATH_TO_PDB_DIR PATH_TO_LMDB_OUTPUT --filetype {pdb,silent,xyz,xyz-gdb} 
```

#### Loading an LMDB dataset

From python:
```
from atom3d.datasets import LMDBDataset

dataset = LMDBDataset(PATH_TO_LMDB)
print(len(dataset))  # Print length
print(dataset[0])  # Print 1st entry
```

From C++:

 We provide example C++ code to load the LMDB datasets [here](https://github.com/drorlab/atom3d/tree/master/atom3d/cpp/lmdb-reader).

### Sharded datasets

An HDF5 based data format that allows for keyed indexing of structures.

#### Loading a sharded dataset

From python:
```
import atom3d.shard.shard as sh

# Load dataset split into fragments (or shards).
sharded = sh.Sharded.load('sharded/candidates/structures@21')

# Iterate through shards.
for shard_num in range(sharded.get_num_shards()):
  structures = sharded.read_shard(shard_num)
  # You can also load associated metadata.
  labels = sharded.read_shard(shard_num, 'labels')
```

## Contribute

* Issue Tracker: https://github.com/drorlab/atom3d/issues
* Source Code: https://github.com/drorlab/atom3d

## Support

If you are having issues, please let us know.
We have a mailing list located at: atom3d@googlegroups.com

## License

The project is licensed under the MIT license.
